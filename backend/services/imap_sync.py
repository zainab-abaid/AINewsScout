"""Pull newsletters from a dedicated IMAP inbox (app password).

Only messages whose From header matches IMAP_ALLOWED_FROM are ingested.
"""

from __future__ import annotations

import hashlib
import imaplib
import logging
import email as email_lib
from datetime import datetime, timedelta
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


_ALLOW_HEADERS = (
    "From",
    "To",
    "Cc",
    "Sender",
    "Delivered-To",
    "Resent-From",
    "X-Forwarded-For",
    "X-Forwarded-To",
)


def headers_allowed(*values: str) -> bool:
    """True when any allowed address appears in the header text.

    Gmail auto-forward keeps the newsletter's original From (for example
    Substack) and records the account that forwarded it in To and
    X-Forwarded-For. Matching only From drops those messages.
    """
    haystack = " ".join(value or "" for value in values).lower()
    return any(allowed in haystack for allowed in IMAP_ALLOWED_FROM)


def _message_allowed(msg: email_lib.message.Message) -> bool:
    values = [_decode_header_value(msg.get(key)) for key in _ALLOW_HEADERS]
    return headers_allowed(*values)


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


def _fetch_bytes(data: Any) -> Optional[bytes]:
    if not data or data[0] is None:
        return None
    part = data[0]
    if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray)):
        return bytes(part[1])
    return None


def _search_candidate_uids(client: imaplib.IMAP4_SSL) -> list[bytes]:
    """Every UID in the folder. Header filtering happens after this.

    SEARCH FROM misses Gmail auto-forwards, whose From stays the newsletter.
    """
    typ, data = client.uid("SEARCH", None, "ALL")
    if typ != "OK" or not data:
        return []
    return [uid for uid in (data[0] or b"").split() if uid]


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
            # Headers first. Already-stored mail is skipped without downloading
            # the body, which is what made every AI search wait on the whole inbox.
            typ, data = client.uid(
                "FETCH",
                uid,
                "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM TO CC SENDER "
                "DELIVERED-TO RESENT-FROM X-FORWARDED-FOR X-FORWARDED-TO)])",
            )
            header = _fetch_bytes(data) if typ == "OK" else None
            if not header:
                counts["skipped"] += 1
                say({"phase": "fetching", "stage": "imap", "current": i, **counts})
                continue
            msg_h = email_lib.message_from_bytes(header)
            if not _message_allowed(msg_h):
                counts["rejected_from"] += 1
                say({"phase": "fetching", "stage": "imap", "current": i, **counts})
                continue
            message_id = (msg_h.get("Message-ID") or msg_h.get("Message-Id") or "").strip()
            gid = _imap_id(message_id, uid)
            if gid in existing_gids or (message_id and message_id in existing_mids):
                counts["skipped"] += 1
                say({"phase": "fetching", "stage": "imap", "current": i, **counts})
                continue

            typ, data = client.uid("FETCH", uid, "(BODY.PEEK[])")
            raw = _fetch_bytes(data) if typ == "OK" else None
            if not raw:
                counts["skipped"] += 1
                say({"phase": "fetching", "stage": "imap", "current": i, **counts})
                continue
            msg = email_lib.message_from_bytes(raw)
            from_addr = _decode_header_value(msg.get("From"))
            message_id = (msg.get("Message-ID") or msg.get("Message-Id") or message_id).strip()
            gid = _imap_id(message_id, uid)
            counts["matched"] += 1

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
    log.info("IMAP sync starting for %s", IMAP_USER)
    counts, new_ids = fetch_and_store()
    log.info("IMAP sync stored %s new emails (%s)", counts.get("new_emails", 0), counts)
    if new_ids:
        # Import lazily: jobs imports this module.
        from backend.services.extract import openai_api_key
        from backend.services.jobs import extract_email_ids

        if openai_api_key():
            log.info("IMAP sync extracting %s new emails", len(new_ids))
            extract_email_ids(new_ids)
        else:
            log.warning(
                "IMAP sync stored %s emails but OPENAI_API_KEY is missing, so they were not extracted",
                len(new_ids),
            )
    return counts
