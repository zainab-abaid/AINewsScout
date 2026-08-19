from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlmodel import select

from backend.database import session_scope
from backend.db import Candidate, Email, Job
from backend.services.extract import dump_raw, extract_candidates
from backend.services.gmail_sync import fetch_and_store, get_label

DONE_STATUSES = {"done", "no_candidates"}
PENDING_STATUSES = {"pending", "failed"}

_running: dict[int, str] = {}


def _now():
    return datetime.now(timezone.utc)


def _update_job(job_id: int, **fields: Any) -> None:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if not job:
            return
        for key, value in fields.items():
            if key == "progress":
                job.progress_json = json.dumps(value)
            else:
                setattr(job, key, value)


def _progress(job_id: int, data: dict[str, Any]) -> None:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if not job:
            return
        try:
            prev = json.loads(job.progress_json or "{}")
        except json.JSONDecodeError:
            prev = {}
        if not isinstance(prev, dict):
            prev = {}
        prev.update(data)
        job.progress_json = json.dumps(prev)


def create_job(kind: str, payload: dict[str, Any]) -> Job:
    with session_scope() as session:
        job = Job(
            kind=kind,
            status="queued",
            payload_json=json.dumps(payload),
            progress_json="{}",
        )
        session.add(job)
        session.flush()
        session.refresh(job)
        return Job(
            id=job.id,
            kind=job.kind,
            status=job.status,
            payload_json=job.payload_json,
            progress_json=job.progress_json,
            error=job.error,
            created_at=job.created_at,
            finished_at=job.finished_at,
        )


def _job_copy(job: Job) -> Job:
    return Job(
        id=job.id,
        kind=job.kind,
        status=job.status,
        payload_json=job.payload_json,
        progress_json=job.progress_json,
        error=job.error,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def get_active_job() -> Optional[Job]:
    with session_scope() as session:
        job = session.exec(
            select(Job)
            .where(Job.status.in_(["queued", "running"]))
            .order_by(Job.id.desc())
        ).first()
        if not job:
            return None
        return _job_copy(job)


def reset_stuck_extractions() -> None:
    with session_scope() as session:
        stuck = session.exec(
            select(Email).where(Email.extraction_status == "running")
        ).all()
        for email in stuck:
            email.extraction_status = "pending"
            email.extraction_error = None


def resume_orphaned_jobs() -> None:
    reset_stuck_extractions()
    with session_scope() as session:
        jobs = session.exec(
            select(Job).where(Job.status.in_(["queued", "running"]))
        ).all()
        items = [(job.id, job.kind) for job in jobs if job.id is not None]
    for job_id, kind in items:
        if job_id in _running:
            continue
        target = run_sync_job if kind == "sync" else run_extract_job
        threading.Thread(target=target, args=(job_id,), daemon=True).start()


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _email_day(email: Email) -> Optional[str]:
    if email.sent_at is None:
        return None
    return email.sent_at.strftime("%Y-%m-%d")


def email_in_range(
    email: Email, date_from: Optional[date], date_to: Optional[date]
) -> bool:
    day = _email_day(email)
    if not day:
        return False
    if date_from and day < date_from.isoformat():
        return False
    if date_to and day > date_to.isoformat():
        return False
    return True


def preview_sync(date_from: Optional[date], date_to: Optional[date]) -> dict[str, Any]:
    with session_scope() as session:
        emails = [
            e
            for e in session.exec(select(Email)).all()
            if email_in_range(e, date_from, date_to)
        ]
        ids = [e.id for e in emails if e.id is not None]
        extracted = sum(1 for e in emails if e.extraction_status in DONE_STATUSES)
        pending = sum(1 for e in emails if e.extraction_status in PENDING_STATUSES)
        failed = sum(1 for e in emails if e.extraction_status == "failed")
        cands = (
            session.exec(select(Candidate).where(Candidate.email_id.in_(ids))).all()
            if ids
            else []
        )
        marked = sum(
            1
            for c in cands
            if c.important or c.shortlisted or bool((c.notes or "").strip())
        )
        return {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "stored": len(emails),
            "extracted": extracted,
            "pending": pending,
            "failed": failed,
            "candidates": len(cands),
            "marked": marked,
            "needs_confirm": extracted > 0,
        }


def emails_in_range(
    date_from: Optional[date], date_to: Optional[date]
) -> list[dict[str, Any]]:
    with session_scope() as session:
        return [
            {"id": e.id, "status": e.extraction_status}
            for e in session.exec(select(Email)).all()
            if e.id is not None and email_in_range(e, date_from, date_to)
        ]


def extract_email_ids(
    ids: list[int],
    job_id: Optional[int] = None,
    overwrite: bool = False,
) -> dict[str, int]:
    counts = {"extracted": 0, "failed": 0, "empty": 0, "skipped": 0}
    total = len(ids)
    for i, eid in enumerate(ids, start=1):
        with session_scope() as session:
            email = session.get(Email, eid)
            if email is None:
                counts["skipped"] += 1
                continue
            if email.extraction_status == "running":
                counts["skipped"] += 1
                continue
            existing = session.exec(
                select(Candidate).where(Candidate.email_id == eid)
            ).all()
            already_done = (
                email.extraction_status in DONE_STATUSES or bool(existing)
            )
            if already_done and not overwrite:
                counts["skipped"] += 1
                continue
            email.extraction_status = "running"
            email.extraction_error = None
            subject = email.subject
            date_raw = email.date_raw
            body = email.body_md
        if job_id is not None:
            _progress(
                job_id,
                {
                    **counts,
                    "phase": "extracting",
                    "stage": "extract",
                    "current": i,
                    "total": total,
                    "email_id": eid,
                    "subject": subject,
                    "activity": "rereading" if overwrite else "reading",
                    "overwrite": overwrite,
                },
            )
        try:
            result = extract_candidates(subject, date_raw, body)
            ideas_this_email: Optional[int] = None
            with session_scope() as session:
                email = session.get(Email, eid)
                if email is None:
                    continue
                existing = session.exec(
                    select(Candidate).where(Candidate.email_id == eid)
                ).all()
                if existing and not overwrite:
                    email.extraction_status = "done"
                    counts["skipped"] += 1
                    continue
                if overwrite:
                    for cand in existing:
                        session.delete(cand)
                    session.flush()
                for cand in result.candidates:
                    session.add(
                        Candidate(
                            email_id=eid,
                            tag=cand.tag.value,
                            topic=cand.topic.strip(),
                            main_idea=cand.main_idea.strip(),
                            excerpt=cand.excerpt.strip(),
                        )
                    )
                email.extraction_status = (
                    "done" if result.candidates else "no_candidates"
                )
                email.raw_model_response = dump_raw(result)
                if result.candidates:
                    counts["extracted"] += 1
                else:
                    counts["empty"] += 1
                ideas_this_email = len(result.candidates)
            if job_id is not None and ideas_this_email is not None:
                _progress(
                    job_id,
                    {
                        **counts,
                        "phase": "extracting",
                        "stage": "extract",
                        "current": i,
                        "total": total,
                        "subject": subject,
                        "activity": "done_email",
                        "ideas_this_email": ideas_this_email,
                        "overwrite": overwrite,
                    },
                )
        except Exception as exc:
            counts["failed"] += 1
            with session_scope() as session:
                email = session.get(Email, eid)
                if email:
                    email.extraction_status = "failed"
                    email.extraction_error = str(exc)[:2000]
    if job_id is not None:
        _progress(
            job_id,
            {**counts, "phase": "done", "total": total, "overwrite": overwrite},
        )
    return counts


def run_extract_job(job_id: int) -> None:
    _running[job_id] = "extract"
    try:
        _update_job(job_id, status="running")
        with session_scope() as session:
            job = session.get(Job, job_id)
            payload = json.loads(job.payload_json) if job else {}
        ids = payload.get("email_ids")
        if not ids:
            with session_scope() as session:
                pending = session.exec(
                    select(Email.id).where(
                        Email.extraction_status.in_(["pending", "failed"])
                    )
                ).all()
                ids = list(pending)
        counts = extract_email_ids(ids, job_id=job_id)
        _update_job(
            job_id,
            status="done",
            finished_at=_now(),
            progress={**counts, "phase": "done"},
        )
    except Exception as exc:
        _update_job(
            job_id, status="failed", error=str(exc)[:2000], finished_at=_now()
        )
    finally:
        _running.pop(job_id, None)


def run_sync_job(job_id: int) -> None:
    _running[job_id] = "sync"
    try:
        _update_job(job_id, status="running")
        with session_scope() as session:
            job = session.get(Job, job_id)
            payload = json.loads(job.payload_json) if job else {}
        date_from = parse_iso_date(payload.get("date_from"))
        date_to = parse_iso_date(payload.get("date_to"))
        label = payload.get("label") or get_label()
        do_extract = payload.get("extract", True)
        overwrite = bool(payload.get("overwrite_extracted"))

        def prog(data: dict[str, Any]) -> None:
            _progress(job_id, data)

        counts, new_ids = fetch_and_store(date_from, date_to, label, prog)
        range_rows = emails_in_range(date_from, date_to)
        already = [r["id"] for r in range_rows if r["status"] in DONE_STATUSES]
        pending = [r["id"] for r in range_rows if r["status"] in PENDING_STATUSES]
        counts["already_extracted"] = len(already)
        counts["overwrite"] = overwrite

        extract_ids: list[int] = []
        seen: set[int] = set()

        def add_ids(values: list[int]) -> None:
            for eid in values:
                if eid not in seen:
                    seen.add(eid)
                    extract_ids.append(eid)

        add_ids(new_ids)
        add_ids(pending)
        if overwrite:
            add_ids(already)

        if do_extract and extract_ids:
            _progress(
                job_id,
                {
                    **counts,
                    "phase": "extracting",
                    "stage": "extract",
                    "current": 0,
                    "total": len(extract_ids),
                    "activity": "starting",
                    "overwrite": overwrite,
                },
            )
            extract_counts = extract_email_ids(
                extract_ids, job_id=job_id, overwrite=overwrite
            )
            counts.update({f"extract_{k}": v for k, v in extract_counts.items()})
        elif do_extract and already and not overwrite:
            counts["extract_skipped"] = len(already)
            counts["skipped_extracted"] = len(already)
            _progress(
                job_id,
                {
                    **counts,
                    "phase": "done",
                    "skipped_extracted": len(already),
                },
            )
        _update_job(
            job_id,
            status="done",
            finished_at=_now(),
            progress={**counts, "phase": "done"},
        )
    except Exception as exc:
        _update_job(
            job_id, status="failed", error=str(exc)[:2000], finished_at=_now()
        )
    finally:
        _running.pop(job_id, None)
