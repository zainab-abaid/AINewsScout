import json
import threading
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select

from backend.config import OPENAI_MODEL, OPENAI_REASONING_EFFORT
from backend.database import session_scope
from backend.db import Email, Job
from backend.schemas import (
    ExtractRequest,
    JobOut,
    SyncPreviewOut,
    SyncRequest,
)
from backend.services.extract import openai_api_key
from backend.services.gmail_sync import (
    auth_url,
    disconnect,
    finish_oauth,
    gmail_status,
)
from backend.services.jobs import (
    create_job,
    get_active_job,
    parse_iso_date,
    preview_sync,
    run_extract_job,
    run_sync_job,
)

router = APIRouter()


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def job_out(job: Job) -> JobOut:
    try:
        payload = json.loads(job.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    try:
        progress = json.loads(job.progress_json or "{}")
    except json.JSONDecodeError:
        progress = {}
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        payload=payload,
        progress=progress,
        error=job.error,
        created_at=_utc(job.created_at),
        finished_at=_utc(job.finished_at),
    )


@router.get("/gmail/connect")
def gmail_connect():
    try:
        url = auth_url()
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"auth_url": url}


@router.get("/gmail/callback")
def gmail_callback(request: Request):
    frontend = "http://127.0.0.1:5173/"
    params = request.query_params
    error = params.get("error")
    code = params.get("code")
    state = params.get("state")
    if error:
        return RedirectResponse(f"{frontend}?gmail=error&detail={quote(error)}")
    if not code:
        return RedirectResponse(f"{frontend}?gmail=error&detail=missing_code")
    try:
        finish_oauth(code, state)
    except Exception as exc:
        return RedirectResponse(
            f"{frontend}?gmail=error&detail={quote(str(exc)[:240])}"
        )
    return RedirectResponse(f"{frontend}?gmail=connected")


@router.post("/gmail/disconnect")
def gmail_disconnect():
    disconnect()
    return gmail_status()


@router.get("/jobs/active", response_model=JobOut | None)
def active_job():
    job = get_active_job()
    if not job:
        return None
    return job_out(job)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int):
    with session_scope() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return job_out(job)


@router.post("/sync/preview", response_model=SyncPreviewOut)
def sync_preview(body: SyncRequest):
    return preview_sync(
        parse_iso_date(body.date_from),
        parse_iso_date(body.date_to),
    )


@router.post("/sync", response_model=JobOut)
def start_sync(body: SyncRequest):
    status = gmail_status()
    if not status.get("connected"):
        raise HTTPException(400, "Connect Gmail first")
    payload = body.model_dump()
    if not payload.get("label"):
        payload["label"] = status.get("label")
    job = create_job("sync", payload)
    threading.Thread(target=run_sync_job, args=(job.id,), daemon=True).start()
    return job_out(job)


@router.post("/extract", response_model=JobOut)
def start_extract(body: ExtractRequest):
    payload = body.model_dump()
    if not openai_api_key():
        raise HTTPException(400, "OPENAI_API_KEY is missing from .env")
    if payload.get("email_ids"):
        ids = payload["email_ids"]
    else:
        with session_scope() as session:
            statuses = ["pending", "failed"] if body.pending_only else None
            stmt = select(Email.id)
            if statuses:
                stmt = stmt.where(Email.extraction_status.in_(statuses))
            ids = list(session.exec(stmt).all())
        payload["email_ids"] = ids
    job = create_job("extract", payload)
    threading.Thread(target=run_extract_job, args=(job.id,), daemon=True).start()
    return job_out(job)


@router.get("/settings/status")
def settings_status():
    gmail = gmail_status()
    key = openai_api_key()
    return {
        **gmail,
        "openai_configured": bool(key),
        "openai_model": OPENAI_MODEL,
        "openai_reasoning_effort": OPENAI_REASONING_EFFORT,
    }
