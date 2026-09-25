import json
import threading
from datetime import timezone

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from backend.auth import require_role
from backend.config import OPENAI_MODEL, OPENAI_REASONING_EFFORT
from backend.database import session_scope
from backend.db import Email, Job
from backend.schemas import ExtractRequest, JobOut, SyncRequest
from backend.services.extract import openai_api_key
from backend.services.imap_sync import imap_configured, imap_status
from backend.services.jobs import (
    create_job,
    get_active_job,
    run_extract_job,
    run_sync_job,
)

router = APIRouter()


def _utc(dt):
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


@router.post("/sync", response_model=JobOut)
def start_sync(body: SyncRequest, _role: str = require_role("analyst")):
    if not imap_configured():
        raise HTTPException(
            400,
            "Inbox is not configured. Set IMAP_USER, IMAP_PASSWORD, and IMAP_ALLOWED_FROM in .env",
        )
    job = create_job("sync", body.model_dump())
    threading.Thread(target=run_sync_job, args=(job.id,), daemon=True).start()
    return job_out(job)


@router.post("/extract", response_model=JobOut)
def start_extract(body: ExtractRequest, _role: str = require_role("analyst")):
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
    inbox = imap_status()
    key = openai_api_key()
    return {
        "inbox_configured": inbox["configured"],
        "inbox_enabled": inbox["enabled"],
        "inbox_email": inbox["user"],
        "inbox_host": inbox["host"],
        "inbox_folder": inbox["folder"],
        "allowed_from": inbox["allowed_from"],
        "sync_hour": inbox["sync_hour"],
        "openai_configured": bool(key),
        "openai_model": OPENAI_MODEL,
        "openai_reasoning_effort": OPENAI_REASONING_EFFORT,
    }
