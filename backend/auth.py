"""Role tokens: locked → viewer → analyst → admin.

Tokens live in environment variables so hosts can inject them as secrets
without committing them to git.

If VIEWER_TOKEN is set, a valid token is required before any content APIs
respond. If it is empty (local convenience), anonymous requests act as viewer.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, Header, HTTPException

from backend.config import ADMIN_TOKEN, ANALYST_TOKEN, VIEWER_TOKEN

Role = Literal["locked", "viewer", "analyst", "admin"]

_RANK = {"locked": -1, "viewer": 0, "analyst": 1, "admin": 2}


def role_from_token(token: str | None) -> Role:
    raw = (token or "").strip()
    if ADMIN_TOKEN and raw == ADMIN_TOKEN:
        return "admin"
    if ANALYST_TOKEN and raw == ANALYST_TOKEN:
        return "analyst"
    if VIEWER_TOKEN and raw == VIEWER_TOKEN:
        return "viewer"
    # Production / shared hosts should set VIEWER_TOKEN. When it is unset,
    # empty requests stay usable locally as a viewer.
    if not VIEWER_TOKEN and not raw:
        return "viewer"
    return "locked"


def tokens_configured() -> dict[str, bool]:
    return {
        "viewer_token_set": bool(VIEWER_TOKEN),
        "analyst_token_set": bool(ANALYST_TOKEN),
        "admin_token_set": bool(ADMIN_TOKEN),
    }


def unlock(token: str) -> Role:
    role = role_from_token(token)
    if role == "locked":
        raise HTTPException(401, "Unrecognised token")
    return role


def require_role(minimum: Role):
    """FastAPI dependency: require at least `minimum` role via X-Access-Token."""

    def _dep(x_access_token: str | None = Header(default=None, alias="X-Access-Token")) -> Role:
        role = role_from_token(x_access_token)
        if _RANK[role] < _RANK[minimum]:
            if minimum == "viewer":
                need = "a valid access token (viewer, analyst, or admin)"
            elif minimum == "analyst":
                need = "an analyst or admin token"
            else:
                need = "an admin token"
            raise HTTPException(403, f"This action needs {need}. Sign in from the header.")
        return role

    return Depends(_dep)
