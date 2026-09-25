"""Role tokens: viewer (default), analyst, admin.

Tokens live in environment variables so hosts can inject them as secrets
without committing them to git.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, Header, HTTPException

from backend.config import ADMIN_TOKEN, ANALYST_TOKEN

Role = Literal["viewer", "analyst", "admin"]

_RANK = {"viewer": 0, "analyst": 1, "admin": 2}


def role_from_token(token: str | None) -> Role:
    raw = (token or "").strip()
    if not raw:
        return "viewer"
    if ADMIN_TOKEN and raw == ADMIN_TOKEN:
        return "admin"
    if ANALYST_TOKEN and raw == ANALYST_TOKEN:
        return "analyst"
    return "viewer"


def tokens_configured() -> dict[str, bool]:
    return {
        "analyst_token_set": bool(ANALYST_TOKEN),
        "admin_token_set": bool(ADMIN_TOKEN),
    }


def unlock(token: str) -> Role:
    role = role_from_token(token)
    if role == "viewer":
        raise HTTPException(401, "Unrecognised token")
    return role


def require_role(minimum: Role):
    """FastAPI dependency: require at least `minimum` role via X-Access-Token."""

    def _dep(x_access_token: str | None = Header(default=None, alias="X-Access-Token")) -> Role:
        role = role_from_token(x_access_token)
        if _RANK[role] < _RANK[minimum]:
            need = "an analyst or admin token" if minimum == "analyst" else "an admin token"
            raise HTTPException(403, f"This action needs {need}. Sign in from the header.")
        return role

    return Depends(_dep)
