from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from sqlmodel import select

from backend.database import session_scope
from backend.db import Candidate, Category, Email, IdeaSearch, IdeaSearchHit, Job
from backend.services.extract import dump_raw, extract_candidates
from backend.services.imap_sync import fetch_and_store, imap_configured
from backend.services.idea_search import (
    SearchEmail,
    chunk_emails,
    readable_model_error,
    search_chunk,
)

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


# Filled in at the bottom of the module, once the runners are defined.
JOB_RUNNERS: dict[str, Callable[[int], None]] = {}

# The sync panel in the UI reattaches to whatever job is active, so a search
# running in its own tab must not surface there. Searches are tracked by their
# own record instead.
PANEL_JOB_KINDS = ["sync", "extract"]


def get_active_job() -> Optional[Job]:
    with session_scope() as session:
        job = session.exec(
            select(Job)
            .where(Job.status.in_(["queued", "running"]))
            .where(Job.kind.in_(PANEL_JOB_KINDS))
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
        target = JOB_RUNNERS.get(kind)
        if target is None:
            continue
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


def preview_sync() -> dict[str, Any]:
    """Local counts only — IMAP listing happens when sync actually runs."""
    with session_scope() as session:
        emails = list(session.exec(select(Email)).all())
        pending = sum(1 for e in emails if e.extraction_status in PENDING_STATUSES)
        return {
            "stored": len(emails),
            "pending": pending,
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


def _load_categories() -> dict[str, int]:
    """Return {category_name_lower: id} for active (non-deprecated) categories."""
    with session_scope() as session:
        rows = session.exec(select(Category)).all()
        return {
            r.name.lower(): r.id
            for r in rows
            if r.id is not None and not getattr(r, "deprecated", False)
        }


def _resolve_category(
    suggested: Optional[str], cat_map: dict[str, int]
) -> Optional[int]:
    """Match the model's suggested category name (case-insensitive) to a DB id."""
    if not suggested:
        return None
    return cat_map.get(suggested.strip().lower())


def extract_email_ids(
    ids: list[int],
    job_id: Optional[int] = None,
    overwrite: bool = False,
) -> dict[str, int]:
    counts = {"extracted": 0, "failed": 0, "empty": 0, "skipped": 0}
    total = len(ids)
    # Fetch categories once for the whole batch; names are passed to the LLM.
    cat_map = _load_categories()
    # Active categories only — deprecated ones stay on old items but are not offered to the model.
    with session_scope() as session:
        category_names_display = [
            r.name
            for r in session.exec(select(Category)).all()
            if not getattr(r, "deprecated", False)
        ]
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
            result = extract_candidates(
                subject, date_raw, body, categories=category_names_display
            )
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
                            category_id=_resolve_category(cand.category, cat_map),
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


def search_emails_in_range(
    date_from: Optional[date], date_to: Optional[date]
) -> list[SearchEmail]:
    """Stored emails a search should read, oldest first."""
    with session_scope() as session:
        rows = [
            e
            for e in session.exec(select(Email)).all()
            if e.id is not None and email_in_range(e, date_from, date_to)
        ]
        rows.sort(key=lambda e: (e.sent_at or datetime.min, e.id or 0))
        return [
            SearchEmail(
                id=e.id,
                subject=e.subject,
                date=_email_day(e) or e.date_raw,
                body_md=e.body_md,
            )
            for e in rows
        ]


def preview_search(
    date_from: Optional[date], date_to: Optional[date]
) -> dict[str, Any]:
    """Search runs over emails already in the local DB (including historic ones).

    If the inbox is configured, the search job also does a quick IMAP pull first
    so brand-new forwards are included — but the preview only reports what is
    already stored, since IMAP listing is not free.
    """
    emails = search_emails_in_range(date_from, date_to)
    stored = len(emails)
    chunks = len(chunk_emails(emails))
    return {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "emails": stored,
        "stored": stored,
        "will_fetch": 0,
        "inbox_configured": imap_configured(),
        "chunks": chunks,
    }


def _search_exists(search_id: int) -> bool:
    with session_scope() as session:
        return session.get(IdeaSearch, search_id) is not None


def _finish_search(search_id: int, **fields: Any) -> None:
    with session_scope() as session:
        search = session.get(IdeaSearch, search_id)
        if not search:
            return
        for key, value in fields.items():
            setattr(search, key, value)


def run_idea_search_job(job_id: int) -> None:
    """Search every batch in the range, storing hits as each batch comes back.

    One failing batch does not lose the rest: it is counted and the search
    carries on, so partial evidence still reaches the user.
    """
    _running[job_id] = "idea_search"
    search_id: Optional[int] = None
    try:
        _update_job(job_id, status="running")
        with session_scope() as session:
            job = session.get(Job, job_id)
            payload = json.loads(job.payload_json) if job else {}
        search_id = payload.get("search_id")
        with session_scope() as session:
            search = session.get(IdeaSearch, search_id) if search_id else None
            if search is None:
                raise RuntimeError("Search not found")
            question = search.question
            date_from = parse_iso_date(search.date_from)
            date_to = parse_iso_date(search.date_to)
            search.status = "running"
            search.error = None
            # A job resumed after a restart starts its batches again, so clear
            # anything the earlier attempt stored rather than doubling it up.
            for old in session.exec(
                select(IdeaSearchHit).where(IdeaSearchHit.search_id == search_id)
            ).all():
                session.delete(old)

        fetch_meta: dict[str, Any] = {}
        if imap_configured():
            if not _search_exists(search_id):
                _update_job(
                    job_id,
                    status="done",
                    finished_at=_now(),
                    progress={"phase": "cancelled"},
                )
                return
            _progress(
                job_id,
                {
                    "phase": "listing",
                    "stage": "download",
                    "listed": 0,
                    "new_emails": 0,
                    "skipped": 0,
                },
            )

            def prog(data: dict[str, Any]) -> None:
                _progress(job_id, data)

            try:
                fetch_counts, _new_ids = fetch_and_store(progress=prog)
            except Exception as exc:
                raise RuntimeError(readable_model_error(exc)) from exc
            _progress(
                job_id,
                {
                    **fetch_counts,
                    "phase": "fetched",
                    "stage": "download",
                },
            )
            if not _search_exists(search_id):
                _update_job(
                    job_id,
                    status="done",
                    finished_at=_now(),
                    progress={**fetch_counts, "phase": "cancelled"},
                )
                return
            fetch_meta = {
                "listed": fetch_counts.get("listed", 0),
                "new_emails": fetch_counts.get("new_emails", 0),
                "skipped": fetch_counts.get("skipped", 0),
            }

        emails = search_emails_in_range(date_from, date_to)
        if not emails:
            raise RuntimeError("No emails in that date range in the local database.")
        chunks = chunk_emails(emails)
        _finish_search(
            search_id, emails_total=len(emails), chunks_total=len(chunks)
        )
        counts = {
            "emails_total": len(emails),
            "chunks_total": len(chunks),
            "chunks_done": 0,
            "chunks_failed": 0,
            "hits": 0,
            **fetch_meta,
        }
        _progress(job_id, {**counts, "phase": "searching", "stage": "search"})

        hits = 0
        failed = 0
        last_error = ""
        cancelled = False
        for index, chunk in enumerate(chunks):
            # Deleting a search is how it gets cancelled, so check before paying
            # for another batch and again before storing what came back.
            if not _search_exists(search_id):
                cancelled = True
                break
            _progress(
                job_id,
                {
                    **counts,
                    "phase": "searching",
                    "stage": "search",
                    "chunks_done": index,
                    "chunks_failed": failed,
                    "hits": hits,
                    "current": index + 1,
                    "total": len(chunks),
                    "subject": chunk[0].subject if chunk else "",
                },
            )
            try:
                findings = search_chunk(question, chunk)
            except Exception as exc:
                failed += 1
                last_error = readable_model_error(exc)[:2000]
                _finish_search(search_id, chunks_failed=failed)
                continue
            if not _search_exists(search_id):
                cancelled = True
                break
            with session_scope() as session:
                for finding in findings:
                    session.add(
                        IdeaSearchHit(
                            search_id=search_id,
                            email_id=finding.email_id,
                            chunk_index=index,
                            relevance=finding.relevance.value,
                            title=finding.title,
                            excerpt=finding.excerpt,
                            why_relevant=finding.why_relevant,
                        )
                    )
            hits += len(findings)
            _finish_search(search_id, chunks_done=index + 1 - failed)
            _progress(
                job_id,
                {
                    **counts,
                    "phase": "searching",
                    "stage": "search",
                    "chunks_done": index + 1,
                    "chunks_failed": failed,
                    "hits": hits,
                    "current": index + 1,
                    "total": len(chunks),
                },
            )

        if cancelled:
            _update_job(
                job_id,
                status="done",
                finished_at=_now(),
                progress={**counts, "phase": "cancelled", "hits": hits},
            )
            return

        every_chunk_failed = bool(chunks) and failed == len(chunks)
        _finish_search(
            search_id,
            status="failed" if every_chunk_failed else "done",
            chunks_done=len(chunks) - failed,
            chunks_failed=failed,
            error=last_error if failed else None,
            finished_at=_now(),
        )
        _update_job(
            job_id,
            status="failed" if every_chunk_failed else "done",
            error=last_error if every_chunk_failed else None,
            finished_at=_now(),
            progress={
                **counts,
                "phase": "done",
                "chunks_done": len(chunks) - failed,
                "chunks_failed": failed,
                "hits": hits,
            },
        )
    except Exception as exc:
        message = str(exc)[:2000]
        if search_id:
            _finish_search(
                search_id, status="failed", error=message, finished_at=_now()
            )
        _update_job(job_id, status="failed", error=message, finished_at=_now())
    finally:
        _running.pop(job_id, None)


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
    """Pull allowed messages from the dedicated IMAP inbox, then extract new ones."""
    _running[job_id] = "sync"
    try:
        _update_job(job_id, status="running")
        with session_scope() as session:
            job = session.get(Job, job_id)
            payload = json.loads(job.payload_json) if job else {}
        do_extract = payload.get("extract", True)

        def prog(data: dict[str, Any]) -> None:
            _progress(job_id, data)

        counts, new_ids = fetch_and_store(progress=prog)

        extract_ids: list[int] = []
        seen: set[int] = set()

        def add_ids(values: list[int]) -> None:
            for eid in values:
                if eid not in seen:
                    seen.add(eid)
                    extract_ids.append(eid)

        add_ids(new_ids)
        with session_scope() as session:
            pending = list(
                session.exec(
                    select(Email.id).where(
                        Email.extraction_status.in_(list(PENDING_STATUSES))
                    )
                ).all()
            )
        add_ids([eid for eid in pending if eid is not None])

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
                },
            )
            extract_counts = extract_email_ids(extract_ids, job_id=job_id)
            counts.update({f"extract_{k}": v for k, v in extract_counts.items()})
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


JOB_RUNNERS.update(
    {
        "sync": run_sync_job,
        "extract": run_extract_job,
        "idea_search": run_idea_search_job,
    }
)
