from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from backend.database import get_session
from backend.db import Candidate, Category, Email, IdeaSearch, IdeaSearchHit, Job, utcnow
from backend.routers.core import to_out
from backend.schemas import (
    ALLOWED_TAGS,
    IdeaSearchCreate,
    IdeaSearchDetailOut,
    IdeaSearchOut,
    KeepHitIn,
    KeepHitOut,
    SearchHitOut,
    SearchPreviewOut,
)
from backend.services.extract import openai_api_key
from backend.services.idea_search import excerpts_match
from backend.services.jobs import (
    create_job,
    parse_iso_date,
    preview_search,
    run_idea_search_job,
)
from backend.services.links import hydrate_excerpt_links

router = APIRouter()

RELEVANCE_RANK = {"direct": 0, "related": 1}


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def search_out(
    search: IdeaSearch, hits_total: int, progress: Optional[dict[str, Any]] = None
) -> IdeaSearchOut:
    progress = progress if isinstance(progress, dict) else {}

    def n(key: str) -> int:
        value = progress.get(key)
        return value if isinstance(value, int) else int(value or 0)

    return IdeaSearchOut(
        id=search.id,
        question=search.question,
        date_from=search.date_from,
        date_to=search.date_to,
        status=search.status,
        emails_total=search.emails_total,
        chunks_total=search.chunks_total,
        chunks_done=search.chunks_done,
        chunks_failed=search.chunks_failed,
        hits_total=hits_total,
        error=search.error,
        created_at=_utc(search.created_at),
        finished_at=_utc(search.finished_at),
        phase=str(progress.get("phase") or search.status),
        listed=n("listed"),
        new_emails=n("new_emails"),
        skipped=n("skipped"),
        current=n("current"),
    )


def _progress_for(session: Session, job_id: Optional[int]) -> dict[str, Any]:
    if not job_id:
        return {}
    job = session.get(Job, job_id)
    if not job:
        return {}
    try:
        data = json.loads(job.progress_json or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _hit_out(hit: IdeaSearchHit, email: Optional[Email]) -> SearchHitOut:
    return SearchHitOut(
        id=hit.id,
        email_id=hit.email_id,
        relevance=hit.relevance,
        title=hit.title,
        excerpt=hydrate_excerpt_links(hit.excerpt, email.body_md if email else ""),
        why_relevant=hit.why_relevant,
        email_title=email.subject if email else "",
        email_date=email.date_raw if email else "",
        date_iso=(
            email.sent_at.strftime("%Y-%m-%d") if email and email.sent_at else ""
        ),
        candidate_id=hit.candidate_id,
    )


@router.post("/searches/preview", response_model=SearchPreviewOut)
def searches_preview(body: IdeaSearchCreate):
    return preview_search(parse_iso_date(body.date_from), parse_iso_date(body.date_to))


@router.post("/searches", response_model=IdeaSearchOut)
def create_search(body: IdeaSearchCreate, session: Session = Depends(get_session)):
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(400, "Enter a question to search for")
    if not openai_api_key():
        raise HTTPException(400, "OPENAI_API_KEY is missing from .env")
    preview = preview_search(
        parse_iso_date(body.date_from), parse_iso_date(body.date_to)
    )
    stored = int(preview.get("stored") or 0)
    will_fetch = int(preview.get("will_fetch") or 0)
    connected = bool(preview.get("gmail_connected"))
    checked = bool(preview.get("gmail_checked"))
    if stored == 0 and not connected:
        raise HTTPException(
            400,
            "No stored emails in that date range. Connect Gmail to pull the missing ones.",
        )
    if stored == 0 and checked and will_fetch == 0:
        raise HTTPException(400, "No emails in that date range in Gmail or locally")

    search = IdeaSearch(
        question=question,
        date_from=body.date_from or None,
        date_to=body.date_to or None,
        emails_total=preview["emails"],
        chunks_total=preview["chunks"],
    )
    session.add(search)
    session.flush()
    session.refresh(search)

    job = create_job("idea_search", {"search_id": search.id})
    search.job_id = job.id
    out = search_out(search, 0)
    session.commit()
    threading.Thread(target=run_idea_search_job, args=(job.id,), daemon=True).start()
    return out


@router.get("/searches", response_model=list[IdeaSearchOut])
def list_searches(session: Session = Depends(get_session)):
    searches = session.exec(select(IdeaSearch).order_by(IdeaSearch.id.desc())).all()
    counts: dict[int, int] = {}
    for hit in session.exec(select(IdeaSearchHit)).all():
        counts[hit.search_id] = counts.get(hit.search_id, 0) + 1
    return [search_out(s, counts.get(s.id, 0), _progress_for(session, s.job_id)) for s in searches]


@router.get("/searches/{search_id}", response_model=IdeaSearchDetailOut)
def get_search(search_id: int, session: Session = Depends(get_session)):
    search = session.get(IdeaSearch, search_id)
    if not search:
        raise HTTPException(404, "Search not found")
    hits = session.exec(
        select(IdeaSearchHit).where(IdeaSearchHit.search_id == search_id)
    ).all()
    emails: dict[int, Email] = {}
    if hits:
        found = session.exec(
            select(Email).where(Email.id.in_([h.email_id for h in hits]))
        ).all()
        emails = {e.id: e for e in found if e.id is not None}
    rows = [_hit_out(h, emails.get(h.email_id)) for h in hits]
    # Newest newsletter first, then direct answers above related context.
    rows.sort(key=lambda r: r.date_iso, reverse=True)
    rows.sort(key=lambda r: RELEVANCE_RANK.get(r.relevance, 9))
    base = search_out(search, len(rows), _progress_for(session, search.job_id))
    return IdeaSearchDetailOut(**base.model_dump(), hits=rows)


def _find_matching_candidate(
    session: Session, email_id: int, excerpt: str
) -> Optional[Candidate]:
    existing = session.exec(
        select(Candidate).where(Candidate.email_id == email_id)
    ).all()
    for cand in existing:
        if excerpts_match(cand.excerpt, excerpt):
            return cand
    return None


@router.post(
    "/searches/{search_id}/hits/{hit_id}/keep",
    response_model=KeepHitOut,
)
def keep_hit(
    search_id: int,
    hit_id: int,
    body: KeepHitIn,
    session: Session = Depends(get_session),
):
    """Turn a search finding into a probe candidate and mark it.

    If the same passage was already extracted, that card is reused rather than
    duplicated, then given the user's tag, category, comment and marks.
    """
    hit = session.get(IdeaSearchHit, hit_id)
    if not hit or hit.search_id != search_id:
        raise HTTPException(404, "Finding not found")
    email = session.get(Email, hit.email_id)
    if not email:
        raise HTTPException(404, "Email not found")

    tag = (body.tag or "").strip()
    if tag not in ALLOWED_TAGS:
        raise HTTPException(400, "Pick High priority, Strong, or Possible")
    if not body.important and not body.shortlisted:
        raise HTTPException(400, "Mark the item important or shortlist it")
    category_id = body.category_id
    if category_id is not None:
        if session.get(Category, category_id) is None:
            raise HTTPException(400, "Unknown category")

    excerpt = hydrate_excerpt_links(hit.excerpt, email.body_md).strip()
    cand = None
    if hit.candidate_id:
        cand = session.get(Candidate, hit.candidate_id)
    if cand is None:
        cand = _find_matching_candidate(session, hit.email_id, excerpt)
    if cand is None:
        cand = Candidate(
            email_id=hit.email_id,
            tag=tag,
            topic=(hit.title or "Search finding").strip() or "Search finding",
            main_idea=(hit.why_relevant or "").strip(),
            excerpt=excerpt,
        )
        session.add(cand)
        session.flush()
    else:
        cand.tag = tag
        # A search keep is how this passage entered the queue; keep the richer
        # quote when the stored excerpt is a shorter cut of the same text.
        if excerpt and len(excerpt) > len(cand.excerpt or ""):
            cand.excerpt = excerpt

    cand.important = body.important
    cand.shortlisted = body.shortlisted
    cand.deleted = False
    cand.category_id = category_id
    cand.notes = (body.notes or "").strip()
    cand.marked_at = utcnow()
    session.add(cand)
    session.flush()
    hit.candidate_id = cand.id
    session.add(hit)
    session.commit()
    session.refresh(cand)
    session.refresh(hit)
    cat = session.get(Category, cand.category_id) if cand.category_id else None
    return KeepHitOut(hit=_hit_out(hit, email), candidate=to_out(cand, email, cat))


@router.delete("/searches/{search_id}")
def delete_search(search_id: int, session: Session = Depends(get_session)):
    search = session.get(IdeaSearch, search_id)
    if not search:
        raise HTTPException(404, "Search not found")
    for hit in session.exec(
        select(IdeaSearchHit).where(IdeaSearchHit.search_id == search_id)
    ).all():
        session.delete(hit)
    session.delete(search)
    session.commit()
    return {"ok": True}
