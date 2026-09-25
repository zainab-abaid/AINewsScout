from __future__ import annotations

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile

from backend.auth import require_role, role_from_token, tokens_configured, unlock
from backend.schemas import (
    AuthStatusOut,
    AuthUnlockIn,
    IngestPreviewOut,
    LlmLogDetailOut,
    LlmLogSummaryOut,
    ResearchContextOut,
    ResearchItemIn,
    ResearchItemOut,
    ResearchItemPatch,
    ResearchNotUsefulIn,
    ResearchNotUsefulOut,
    ResearchPriorityIn,
    ResearchPriorityOut,
    ResearchPriorityPatch,
    UrlIngestIn,
)
from backend.services import content_ingest
from backend.services import research_context as rc
from backend.services.llm_logs import get_llm_log, list_llm_logs

router = APIRouter()


def _ctx_out() -> ResearchContextOut:
    data = rc.load_research_context()
    return ResearchContextOut(
        probes=data.get("probes") or [],
        artifacts=data.get("artifacts") or [],
        priority_areas=data.get("priority_areas") or [],
        not_useful=data.get("not_useful") or [],
        source=str(data.get("source") or "database"),
        prompt_preview=rc.research_context_markdown(data),
    )


@router.get("/auth/status", response_model=AuthStatusOut)
def auth_status(x_access_token: str | None = Header(default=None, alias="X-Access-Token")):
    cfg = tokens_configured()
    return AuthStatusOut(
        role=role_from_token(x_access_token),
        viewer_token_set=cfg["viewer_token_set"],
        analyst_token_set=cfg["analyst_token_set"],
        admin_token_set=cfg["admin_token_set"],
    )


@router.post("/auth/unlock", response_model=AuthStatusOut)
def auth_unlock(body: AuthUnlockIn):
    role = unlock(body.token)
    cfg = tokens_configured()
    return AuthStatusOut(
        role=role,
        viewer_token_set=cfg["viewer_token_set"],
        analyst_token_set=cfg["analyst_token_set"],
        admin_token_set=cfg["admin_token_set"],
    )


@router.get("/admin/research-context", response_model=ResearchContextOut)
def get_research_context(_role: str = require_role("admin")):
    return _ctx_out()


# --- Priorities ----------------------------------------------------------------

@router.post("/admin/priorities", response_model=ResearchPriorityOut)
def create_priority(body: ResearchPriorityIn, _role: str = require_role("admin")):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name required")
    return rc.add_priority(name=name, description=body.description)


@router.patch("/admin/priorities/{priority_id}", response_model=ResearchPriorityOut)
def patch_priority(
    priority_id: int, body: ResearchPriorityPatch, _role: str = require_role("admin")
):
    updated = rc.update_priority(
        priority_id, name=body.name, description=body.description
    )
    if not updated:
        raise HTTPException(404, "Priority not found")
    return updated


@router.delete("/admin/priorities/{priority_id}")
def remove_priority(priority_id: int, _role: str = require_role("admin")):
    if not rc.delete_priority(priority_id):
        raise HTTPException(404, "Priority not found")
    return {"ok": True}


# --- Probes --------------------------------------------------------------------

@router.post("/admin/probes", response_model=ResearchItemOut)
def create_probe(body: ResearchItemIn, _role: str = require_role("admin")):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Title required")
    return rc.add_probe(title=title, description=body.description, source_kind="manual")


@router.patch("/admin/probes/{probe_id}", response_model=ResearchItemOut)
def patch_probe(probe_id: int, body: ResearchItemPatch, _role: str = require_role("admin")):
    updated = rc.update_probe(probe_id, title=body.title, description=body.description)
    if not updated:
        raise HTTPException(404, "Probe not found")
    return updated


@router.delete("/admin/probes/{probe_id}")
def remove_probe(probe_id: int, _role: str = require_role("admin")):
    if not rc.delete_probe(probe_id):
        raise HTTPException(404, "Probe not found")
    return {"ok": True}


@router.post("/admin/probes/ingest-url", response_model=IngestPreviewOut)
def ingest_probe_url(body: UrlIngestIn, _role: str = require_role("admin")):
    try:
        text = content_ingest.extract_text_from_url(body.url)
        summary = content_ingest.summarise_source(
            kind="probe", source_text=text, source_label=body.url
        )
        saved = rc.add_probe(
            title=summary.title,
            description=summary.description,
            source_url=body.url.strip(),
            source_kind="url",
        )
        return IngestPreviewOut(
            title=saved["title"],
            description=saved["description"],
            source_url=saved.get("source_url"),
            source_kind=saved["source_kind"],
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/admin/probes/ingest-pdf", response_model=IngestPreviewOut)
async def ingest_probe_pdf(
    file: UploadFile = File(...),
    _role: str = require_role("admin"),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    name = file.filename or "upload.pdf"
    try:
        text = content_ingest.extract_text_from_pdf(raw)
        summary = content_ingest.summarise_source(
            kind="probe", source_text=text, source_label=name
        )
        saved = rc.add_probe(
            title=summary.title,
            description=summary.description,
            source_url=name,
            source_kind="pdf",
        )
        return IngestPreviewOut(
            title=saved["title"],
            description=saved["description"],
            source_url=saved.get("source_url"),
            source_kind=saved["source_kind"],
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


# --- Artifacts -----------------------------------------------------------------

@router.post("/admin/artifacts", response_model=ResearchItemOut)
def create_artifact(body: ResearchItemIn, _role: str = require_role("admin")):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Title required")
    return rc.add_artifact(title=title, description=body.description, source_kind="manual")


@router.patch("/admin/artifacts/{artifact_id}", response_model=ResearchItemOut)
def patch_artifact(
    artifact_id: int, body: ResearchItemPatch, _role: str = require_role("admin")
):
    updated = rc.update_artifact(
        artifact_id, title=body.title, description=body.description
    )
    if not updated:
        raise HTTPException(404, "Artifact not found")
    return updated


@router.delete("/admin/artifacts/{artifact_id}")
def remove_artifact(artifact_id: int, _role: str = require_role("admin")):
    if not rc.delete_artifact(artifact_id):
        raise HTTPException(404, "Artifact not found")
    return {"ok": True}


@router.post("/admin/artifacts/ingest-url", response_model=IngestPreviewOut)
def ingest_artifact_url(body: UrlIngestIn, _role: str = require_role("admin")):
    try:
        text = content_ingest.extract_text_from_url(body.url)
        summary = content_ingest.summarise_source(
            kind="artifact", source_text=text, source_label=body.url
        )
        saved = rc.add_artifact(
            title=summary.title,
            description=summary.description,
            source_url=body.url.strip(),
            source_kind="url",
        )
        return IngestPreviewOut(
            title=saved["title"],
            description=saved["description"],
            source_url=saved.get("source_url"),
            source_kind=saved["source_kind"],
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


# --- Not useful ----------------------------------------------------------------

@router.post("/admin/not-useful", response_model=ResearchNotUsefulOut)
def create_not_useful(body: ResearchNotUsefulIn, _role: str = require_role("admin")):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Text required")
    return rc.add_not_useful(text)


@router.patch("/admin/not-useful/{item_id}", response_model=ResearchNotUsefulOut)
def patch_not_useful(
    item_id: int, body: ResearchNotUsefulIn, _role: str = require_role("admin")
):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Text required")
    updated = rc.update_not_useful(item_id, text)
    if not updated:
        raise HTTPException(404, "Item not found")
    return updated


@router.delete("/admin/not-useful/{item_id}")
def remove_not_useful(item_id: int, _role: str = require_role("admin")):
    if not rc.delete_not_useful(item_id):
        raise HTTPException(404, "Item not found")
    return {"ok": True}


# --- LLM logs ------------------------------------------------------------------

@router.get("/admin/llm-logs", response_model=list[LlmLogSummaryOut])
def llm_logs(
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _role: str = require_role("admin"),
):
    return list_llm_logs(kind=kind, limit=limit)


@router.get("/admin/llm-logs/{log_id}", response_model=LlmLogDetailOut)
def llm_log_detail(log_id: int, _role: str = require_role("admin")):
    row = get_llm_log(log_id)
    if not row:
        raise HTTPException(404, "Log not found")
    return row
