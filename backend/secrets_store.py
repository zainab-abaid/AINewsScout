from __future__ import annotations

import json
from typing import Any, Optional

import keyring

from backend.config import (
    DATA_DIR,
    GMAIL_CLIENT_ID,
    GMAIL_CLIENT_PATH,
    GMAIL_CLIENT_SECRET,
    KEYRING_SERVICE,
    ensure_data_dir,
)


GMAIL_TOKEN_KEY = "gmail_refresh_token_json"
GMAIL_TOKEN_PATH = DATA_DIR / "gmail_token.json"


def get_secret(name: str) -> Optional[str]:
    try:
        return keyring.get_password(KEYRING_SERVICE, name)
    except Exception:
        return None


def set_secret(name: str, value: str) -> None:
    try:
        keyring.set_password(KEYRING_SERVICE, name, value)
    except Exception:
        pass


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, name)
    except Exception:
        pass


def load_gmail_token() -> Optional[dict[str, Any]]:
    raw = get_secret(GMAIL_TOKEN_KEY)
    if not raw and GMAIL_TOKEN_PATH.is_file():
        raw = GMAIL_TOKEN_PATH.read_text(encoding="utf-8")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def save_gmail_token(data: dict[str, Any]) -> None:
    payload = json.dumps(data)
    set_secret(GMAIL_TOKEN_KEY, payload)
    ensure_data_dir()
    GMAIL_TOKEN_PATH.write_text(payload, encoding="utf-8")
    try:
        GMAIL_TOKEN_PATH.chmod(0o600)
    except OSError:
        pass


def clear_gmail_token() -> None:
    delete_secret(GMAIL_TOKEN_KEY)
    if GMAIL_TOKEN_PATH.is_file():
        GMAIL_TOKEN_PATH.unlink()


def load_gmail_client() -> Optional[dict[str, Any]]:
    if GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET:
        return {
            "client_id": GMAIL_CLIENT_ID,
            "client_secret": GMAIL_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [],
        }
    if GMAIL_CLIENT_PATH.is_file():
        try:
            data = json.loads(GMAIL_CLIENT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("client_id") and data.get("client_secret"):
                return data
        except json.JSONDecodeError:
            pass
    return None


def client_config_for_flow(redirect_uri: str) -> dict[str, Any]:
    stored = load_gmail_client()
    if not stored:
        raise RuntimeError("Gmail OAuth client is not configured")
    return {
        "web": {
            "client_id": stored["client_id"],
            "client_secret": stored.get("client_secret", ""),
            "auth_uri": stored.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": stored.get("token_uri", "https://oauth2.googleapis.com/token"),
            "redirect_uris": [redirect_uri],
        }
    }
