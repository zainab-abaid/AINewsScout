"""Pull newsletters from a dedicated IMAP inbox (app password).

Only messages whose From header matches IMAP_ALLOWED_FROM are ingested.
"""

from __future__ import annotations

import hashlib
import imaplib
import logging
import email as email_lib
from datetime import datetime, timedelta
from email.utils import parseaddr
from typing import Any, Callable, Optional

from sqlmodel import select

from backend.config import (
    IMAP_ALLOWED_FROM,
    IMAP_FOLDER,
    IMAP_HOST,
    IMAP_PASSWORD,
    IMAP_PORT,
    IMAP_SYNC_ENABLED,
    IMAP_SYNC_HOUR,
    IMAP_USER,
)
from backend.database import session_scope
from backend.db import Email
from backend.services.mailparse import (
    _decode_header_value,
    parse_date,
    rfc822_message_markdown,
)

log = logging.getLogger(__name__)


def imap_configured() -> bool:
    return bool(IMAP_USER and IMAP_PASSWORD and IMAP_HOST and IMAP_ALLOWED_FROM)


def imap_status() -> dict[str, Any]:
    return {
        "configured": imap_configured(),
        "enabled": IMAP_SYNC_ENABLED and imap_configured(),
        "user": IMAP_USER or None,
        "host": IMAP_HOST,
        "folder": IMAP_FOLDER,
        "allowed_from": list(IMAP_ALLOWED_FROM),
        "sync_hour": IMAP_SYNC_HOUR,
    }


def _from_allowed(from_header: str) -> bool:
    _, addr = parseaddr(from_header or "")
    haystack = f"{from_header or ''} {addr}".lower()
    return any(allowed in haystack for allowed in IMAP_ALLOWED_FROM)


def _imap_id(message_id: str, uid: bytes) -> str:
    raw = (message_id or "").strip() or f"uid:{uid.decode('ascii', errors='replace')}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"imap:{digest}"


def _connect() -> imaplib.IMAP4_SSL:
    if not imap_configured():
        raise RuntimeError(
            "IMAP is not configured — set IMAP_USER, IMAP_PASSWORD, and IMAP_ALLOWED_FROM in .env"
        )
    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    client.login(IMAP_USER, IMAP_PASSWORD)
    return client


def _search_candidate_uids(client: imaplib.IMAP4_SSL) -> list[bytes]:
    """List UIDs that might match an allowed From address.

    IMAP SEARCH FROM is approximate; we still filter on the header.
    """
    seen: set[bytes] = set()
    ordered: list[bytes] = []
    for allowed in IMAP_ALLOWED_FROM:
        # Prefer the address local@domain form for SEARCH.
        needle = allowed
        typ, data = client.uid("SEARCH", None, "FROM", f'"{needle}"')
        if typ != "OK":
            continue
        for uid in (data[0] or b"").split():
            if uid and uid not in seen:
                seen.add(uid)
                ordered.append(uid)
    return ordered


def fetch_and_store(
    progress: Optional[Callable[[dict[str, Any]], None]] = None,
    *,
    dry_run: bool = False,
) -> tuple[dict[str, int], list[int]]:
    """Download allowed-from messages and store new ones.

    Dedupes on rfc822 Message-ID and on a stable `imap:…` gmail_id.
    """
    say = progress or (lambda _p: None)
    counts = {
        "listed": 0,
        "matched": 0,
        "new_emails": 0,
        "skipped": 0,
        "rejected_from": 0,
    }
    new_ids: list[int] = []
    say({"phase": "connecting", "stage": "imap", **counts})

    client = _connect()
    try:
        typ, _ = client.select(IMAP_FOLDER, readonly=True)
        if typ != "OK":
            raise RuntimeError(f"Cannot select IMAP folder {IMAP_FOLDER!r}")
        uids = _search_candidate_uids(client)
        counts["listed"] = len(uids)
        say({"phase": "fetching", "stage": "imap", **counts})

        with session_scope() as session:
            existing_gids = {
                gid for gid in session.exec(select(Email.gmail_id)).all() if gid
            }
            existing_mids = {
                mid
                for mid in session.exec(select(Email.rfc822_message_id)).all()
                if mid
            }

        for i, uid in enumerate(uids, start=1):
            typ, data = client.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not data or data[0] is None:
                counts["skipped"] += 1
                say({"phase": "fetching", "stage": "imap", "current": i, **counts})
                continue
            raw = data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                counts["skipped"] += 1
                continue
            msg = email_lib.message_from_bytes(bytes(raw))
            from_addr = _decode_header_value(msg.get("From"))
            if not _from_allowed(from_addr):
                counts["rejected_from"] += 1
                say({"phase": "fetching", "stage": "imap", "current": i, **counts})
                continue
            counts["matched"] += 1
            message_id = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
            gid = _imap_id(message_id, uid)
            if gid in existing_gids or (message_id and message_id in existing_mids):
                counts["skipped"] += 1
                say({"phase": "fetching", "stage": "imap", "current": i, **counts})
                continue

            subject = _decode_header_value(msg.get("Subject")) or "(no subject)"
            date_raw = msg.get("Date") or ""
            md = rfc822_message_markdown(msg, f"imap:{IMAP_FOLDER}")
            sent_at = parse_date(date_raw)

            if dry_run:
                counts["new_emails"] += 1
                say(
                    {
                        "phase": "fetching",
                        "stage": "imap",
                        "current": i,
                        "dry_run_subject": subject[:80],
                        **counts,
                    }
                )
                continue

            with session_scope() as session:
                dup = None
                if message_id:
                    dup = session.exec(
                        select(Email).where(Email.rfc822_message_id == message_id)
                    ).first()
                if dup is not None:
                    if not dup.gmail_id:
                        dup.gmail_id = gid
                    counts["skipped"] += 1
                else:
                    row = Email(
                        gmail_id=gid,
                        rfc822_message_id=message_id or None,
                        subject=subject,
                        from_addr=from_addr,
                        sent_at=sent_at,
                        date_raw=date_raw,
                        body_md=md,
                        source_path=None,
                        extraction_status="pending",
                    )
                    session.add(row)
                    session.flush()
                    if row.id:
                        new_ids.append(row.id)
                    counts["new_emails"] += 1
                    existing_gids.add(gid)
                    if message_id:
                        existing_mids.add(message_id)
            say({"phase": "fetching", "stage": "imap", "current": i, **counts})

        say({"phase": "fetched", "stage": "imap", **counts})
        return counts, new_ids
    finally:
        try:
            client.logout()
        except Exception:
            pass


def seconds_until_sync_hour(now: Optional[datetime] = None) -> float:
    """Seconds until the next local IMAP_SYNC_HOUR:00."""
    now = now or datetime.now().astimezone()
    target = now.replace(hour=IMAP_SYNC_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def run_imap_sync_once() -> dict[str, int]:
    if not (IMAP_SYNC_ENABLED and imap_configured()):
        log.info("IMAP daily sync skipped (disabled or not configured)")
        return {}
    log.info(
        "IMAP sync starting for %s (allowed_from=%s)",
        IMAP_USER,
        IMAP_ALLOWED_FROM,
    )
    counts, new_ids = fetch_and_store()
    log.info("IMAP sync done: %s new_ids=%s", counts, new_ids)
    return counts
