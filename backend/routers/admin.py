from __future__ import annotations

from fastapi import APIRouter, Header

from backend.auth import require_role, role_from_token, tokens_configured, unlock
from backend.schemas import AuthStatusOut, AuthUnlockIn, ResearchContextIn, ResearchContextOut
from backend.services.research_context import load_research_context, save_research_context

router = APIRouter()


@router.get("/auth/status", response_model=AuthStatusOut)
def auth_status(x_access_token: str | None = Header(default=None, alias="X-Access-Token")):
    cfg = tokens_configured()
    return AuthStatusOut(
        role=role_from_token(x_access_token),
        analyst_token_set=cfg["analyst_token_set"],
        admin_token_set=cfg["admin_token_set"],
    )


@router.post("/auth/unlock", response_model=AuthStatusOut)
def auth_unlock(body: AuthUnlockIn):
    role = unlock(body.token)
    cfg = tokens_configured()
    return AuthStatusOut(
        role=role,
        analyst_token_set=cfg["analyst_token_set"],
        admin_token_set=cfg["admin_token_set"],
    )


@router.get("/admin/research-context", response_model=ResearchContextOut)
def get_research_context(_role: str = require_role("admin")):
    data = load_research_context()
    return ResearchContextOut(
        priority_areas=data.get("priority_areas") or [],
        past_probes=data.get("past_probes") or [],
        not_useful=data.get("not_useful") or [],
        source=str(data.get("source") or "skill_file"),
    )


@router.put("/admin/research-context", response_model=ResearchContextOut)
def put_research_context(body: ResearchContextIn, _role: str = require_role("admin")):
    saved = save_research_context(body.model_dump())
    return ResearchContextOut(
        priority_areas=saved.get("priority_areas") or [],
        past_probes=saved.get("past_probes") or [],
        not_useful=saved.get("not_useful") or [],
        source=str(saved.get("source") or "database"),
    )
