from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Callable, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlmodel import select

from backend.config import (
    DATA_DIR,
    GMAIL_LABEL,
    GMAIL_SCOPES,
    ensure_data_dir,
    gmail_redirect_uri,
)
from backend.database import session_scope
from backend.db import AppSetting, Email
from backend.secrets_store import (
    clear_gmail_token,
    client_config_for_flow,
    load_gmail_client,
    load_gmail_token,
    save_gmail_token,
)
from backend.services.mailparse import (
    format_email_markdown,
    gmail_payload_text,
    headers_map,
    parse_date,
)

_STATE_PATH = DATA_DIR / "gmail_oauth_state.json"


def _save_oauth_state(state: str, code_verifier: str | None) -> None:
    ensure_data_dir()
    payload = {"state": state, "code_verifier": code_verifier or ""}
    _STATE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    try:
        _STATE_PATH.chmod(0o600)
    except OSError:
        pass


def _load_oauth_state() -> dict[str, str]:
    if not _STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_label() -> str:
    return GMAIL_LABEL


def credentials_from_store() -> Optional[Credentials]:
    token = load_gmail_token()
    client = load_gmail_client()
    if not token or not client:
        return None
    creds = Credentials(
        token=token.get("token"),
        refresh_token=token.get("refresh_token"),
        token_uri=token.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=client.get("client_id"),
        client_secret=client.get("client_secret"),
        scopes=GMAIL_SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        persist_credentials(creds)
    return creds


def persist_credentials(creds: Credentials) -> None:
    save_gmail_token(
        {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }
    )


def get_cached_email() -> Optional[str]:
    with session_scope() as session:
        row = session.get(AppSetting, "gmail_email")
        return (row.value if row else "") or None


def set_cached_email(email: str) -> None:
    email = (email or "").strip()
    if not email:
        return
    with session_scope() as session:
        row = session.get(AppSetting, "gmail_email")
        if row is None:
            session.add(AppSetting(key="gmail_email", value=email))
        else:
            row.value = email


def gmail_status() -> dict[str, Any]:
    client = load_gmail_client()
    token = load_gmail_token()
    has_refresh = bool(token and token.get("refresh_token"))
    return {
        "connected": bool(client and has_refresh),
        "email": get_cached_email(),
        "has_client": bool(client and client.get("client_id") and client.get("client_secret")),
        "redirect_uri": gmail_redirect_uri(),
        "label": get_label(),
        "scopes": GMAIL_SCOPES,
    }


def auth_url() -> str:
    redirect = gmail_redirect_uri()
    flow = Flow.from_client_config(
        client_config_for_flow(redirect),
        scopes=GMAIL_SCOPES,
        redirect_uri=redirect,
    )
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _save_oauth_state(state, flow.code_verifier)
    return url


def finish_oauth(code: str, state: Optional[str]) -> None:
    saved = _load_oauth_state()
    expected = saved.get("state")
    verifier = saved.get("code_verifier") or None
    if expected and state and state != expected:
        raise RuntimeError("OAuth state mismatch — click Connect Gmail again")
    if not verifier:
        raise RuntimeError("Missing PKCE code verifier — click Connect Gmail again")
    redirect = gmail_redirect_uri()
    flow = Flow.from_client_config(
        client_config_for_flow(redirect),
        scopes=GMAIL_SCOPES,
        redirect_uri=redirect,
        state=state or expected,
        code_verifier=verifier,
        autogenerate_code_verifier=False,
    )
    flow.code_verifier = verifier
    flow.fetch_token(code=code)
    persist_credentials(flow.credentials)
    try:
        service = build("gmail", "v1", credentials=flow.credentials, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        set_cached_email(profile.get("emailAddress") or "")
    except Exception:
        pass
    if _STATE_PATH.is_file():
        _STATE_PATH.unlink()


def disconnect() -> None:
    clear_gmail_token()
    with session_scope() as session:
        row = session.get(AppSetting, "gmail_email")
        if row:
            session.delete(row)


def warmup_gmail_email() -> None:
    if get_cached_email():
        return
    try:
        _service()
    except Exception:
        pass


def _service():
    creds = credentials_from_store()
    if not creds or not creds.valid:
        raise RuntimeError("Gmail is not connected")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    if not get_cached_email():
        try:
            profile = service.users().getProfile(userId="me").execute()
            set_cached_email(profile.get("emailAddress") or "")
        except Exception:
            pass
    return service


def gmail_query(date_from: Optional[date], date_to: Optional[date], label: str) -> str:
    parts = [f"label:{label}"]
    if date_from:
        parts.append(f"after:{date_from.strftime('%Y/%m/%d')}")
    if date_to:
        exclusive = date_to + timedelta(days=1)
        parts.append(f"before:{exclusive.strftime('%Y/%m/%d')}")
    return " ".join(parts)


def list_message_ids(q: str) -> list[str]:
    service = _service()
    ids: list[str] = []
    page = None
    while True:
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=q, pageToken=page, maxResults=500)
            .execute()
        )
        for item in resp.get("messages") or []:
            if item.get("id"):
                ids.append(item["id"])
        page = resp.get("nextPageToken")
        if not page:
            break
    return ids


def fetch_and_store(
    date_from: Optional[date],
    date_to: Optional[date],
    label: str,
    progress: Callable[[dict[str, Any]], None],
) -> tuple[dict[str, int], list[int]]:
    q = gmail_query(date_from, date_to, label)
    progress({"phase": "listing", "stage": "download", "query": q, "listed": 0, "new_emails": 0, "skipped": 0})
    ids = list_message_ids(q)
    counts = {"listed": len(ids), "new_emails": 0, "skipped": 0}
    new_ids: list[int] = []
    progress({**counts, "phase": "fetching", "stage": "download", "query": q})

    with session_scope() as session:
        existing = {
            gid
            for gid in session.exec(select(Email.gmail_id)).all()
            if gid
        }
    service = _service()
    for i, gid in enumerate(ids, start=1):
        if gid in existing:
            counts["skipped"] += 1
            progress({**counts, "phase": "fetching", "stage": "download", "current": i})
            continue
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=gid, format="full")
            .execute()
        )
        payload = msg.get("payload") or {}
        headers = headers_map(payload)
        subject = headers.get("subject") or "(no subject)"
        from_addr = headers.get("from") or ""
        to_addr = headers.get("to") or ""
        date_raw = headers.get("date") or ""
        message_id = (headers.get("message-id") or "").strip()
        body = gmail_payload_text(payload)
        md = format_email_markdown(
            subject, from_addr, date_raw, body, label, message_id, to_addr
        )
        sent_at = parse_date(date_raw)
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
                existing.add(gid)
        progress({**counts, "phase": "fetching", "stage": "download", "current": i})
    progress({**counts, "phase": "fetched", "stage": "download"})
    return counts, new_ids
