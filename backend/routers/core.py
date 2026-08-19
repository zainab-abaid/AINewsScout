from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, func, select

from backend.database import get_session
from backend.db import Candidate, Category, Email
from backend.services.links import hydrate_excerpt_links, normalize_inline_links
from backend.schemas import (
    ALLOWED_TAGS,
    CandidateOut,
    CandidatePatch,
    CategoryCreate,
    CategoryOut,
    EmailOut,
    StatsOut,
    tag_slug,
)

router = APIRouter()

TAG_RANK = {tag: rank for rank, tag in enumerate(ALLOWED_TAGS)}


def _iso(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d")


def _processed(c: Candidate) -> bool:
    return bool(c.important or c.shortlisted or c.deleted)


def to_out(c: Candidate, email: Email, cat: Optional[Category]) -> CandidateOut:
    return CandidateOut(
        id=c.id,
        email_id=c.email_id,
        tag=c.tag,
        tag_slug=tag_slug(c.tag),
        topic=c.topic,
        main_idea=c.main_idea,
        excerpt=hydrate_excerpt_links(c.excerpt, email.body_md),
        important=c.important,
        shortlisted=c.shortlisted,
        deleted=c.deleted,
        processed=_processed(c),
        category_id=c.category_id,
        category_name=cat.name if cat else "",
        notes=c.notes or "",
        email_title=email.subject,
        email_date=email.date_raw or _iso(email.sent_at),
        date_iso=_iso(email.sent_at),
        from_addr=email.from_addr,
    )


@router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(
    status: str = Query("unprocessed"),
    tag: Optional[str] = None,
    category_id: Optional[int] = None,
    uncategorised: bool = False,
    q: str = "",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    session: Session = Depends(get_session),
):
    stmt = (
        select(Candidate, Email, Category)
        .join(Email, Candidate.email_id == Email.id)
        .outerjoin(Category, Candidate.category_id == Category.id)
    )
    rows = session.exec(stmt).all()
    qn = q.strip().lower()
    out: list[CandidateOut] = []
    for cand, email, cat in rows:
        item = to_out(cand, email, cat)
        processed = item.processed
        if status == "unprocessed" and processed:
            continue
        if status == "processed" and not processed:
            continue
        if status == "important" and not item.important:
            continue
        if status == "shortlist" and not item.shortlisted:
            continue
        if status == "deleted" and not item.deleted:
            continue
        if tag and item.tag_slug != tag and item.tag != tag:
            continue
        if category_id is not None and item.category_id != category_id:
            continue
        if uncategorised and item.category_id:
            continue
        if date_from and item.date_iso and item.date_iso < date_from:
            continue
        if date_to and item.date_iso and item.date_iso > date_to:
            continue
        if qn:
            blob = " ".join(
                [item.topic, item.main_idea, item.excerpt, item.email_title]
            ).lower()
            if qn not in blob:
                continue
        out.append(item)

    # Strongest tag first, newest first within a tag. Python's sort is stable,
    # so the passes compose from least to most significant key.
    out.sort(key=lambda c: c.topic)
    out.sort(key=lambda c: c.date_iso or "", reverse=True)
    out.sort(key=lambda c: TAG_RANK.get(c.tag, len(TAG_RANK)))
    return out


@router.patch("/candidates/{candidate_id}", response_model=CandidateOut)
def patch_candidate(
    candidate_id: int,
    body: CandidatePatch,
    session: Session = Depends(get_session),
):
    cand = session.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "Candidate not found")
    if body.important is not None:
        cand.important = body.important
    if body.shortlisted is not None:
        cand.shortlisted = body.shortlisted
    if body.deleted is not None:
        cand.deleted = body.deleted
    if body.clear_category:
        cand.category_id = None
    elif body.category_id is not None:
        cat = session.get(Category, body.category_id)
        if not cat:
            raise HTTPException(400, "Unknown category")
        cand.category_id = body.category_id
    if body.notes is not None:
        cand.notes = body.notes
    session.add(cand)
    session.commit()
    session.refresh(cand)
    email = session.get(Email, cand.email_id)
    cat = session.get(Category, cand.category_id) if cand.category_id else None
    return to_out(cand, email, cat)


@router.get("/emails/{email_id}", response_model=EmailOut)
def get_email(email_id: int, session: Session = Depends(get_session)):
    email = session.get(Email, email_id)
    if not email:
        raise HTTPException(404, "Email not found")
    return EmailOut(
        id=email.id,
        subject=email.subject,
        from_addr=email.from_addr,
        date_raw=email.date_raw,
        date_iso=_iso(email.sent_at),
        body_md=normalize_inline_links(email.body_md),
        extraction_status=email.extraction_status,
        extraction_error=email.extraction_error,
        gmail_id=email.gmail_id,
    )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(session: Session = Depends(get_session)):
    rows = session.exec(select(Category).order_by(Category.sort_order, Category.name)).all()
    return [
        CategoryOut(id=r.id, name=r.name, is_default=r.is_default, sort_order=r.sort_order)
        for r in rows
    ]


@router.post("/categories", response_model=CategoryOut)
def create_category(body: CategoryCreate, session: Session = Depends(get_session)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name required")
    existing = session.exec(select(Category).where(Category.name == name)).first()
    if existing:
        return CategoryOut(
            id=existing.id,
            name=existing.name,
            is_default=existing.is_default,
            sort_order=existing.sort_order,
        )
    max_order = session.exec(select(func.max(Category.sort_order))).one() or 0
    row = Category(name=name, is_default=False, sort_order=int(max_order) + 1)
    session.add(row)
    session.commit()
    session.refresh(row)
    return CategoryOut(
        id=row.id, name=row.name, is_default=row.is_default, sort_order=row.sort_order
    )


@router.get("/stats", response_model=StatsOut)
def stats(session: Session = Depends(get_session)):
    emails = session.exec(select(func.count(Email.id))).one()
    pending = session.exec(
        select(func.count(Email.id)).where(
            Email.extraction_status.in_(["pending", "failed"])
        )
    ).one()
    with_c = session.exec(
        select(func.count(func.distinct(Candidate.email_id)))
    ).one()
    cands = session.exec(select(Candidate)).all()
    dates = [
        e.sent_at
        for e in session.exec(select(Email)).all()
        if e.sent_at is not None
    ]
    def count_tag(tag: str) -> int:
        return sum(1 for c in cands if c.tag == tag)

    unprocessed = sum(
        1 for c in cands if not (c.important or c.shortlisted or c.deleted)
    )
    return StatsOut(
        emails=int(emails or 0),
        emails_with_candidates=int(with_c or 0),
        emails_pending_extraction=int(pending or 0),
        candidates=len(cands),
        high_priority=count_tag("HIGH PRIORITY RESEARCH AREA"),
        strong=count_tag("STRONG CANDIDATE"),
        possible=count_tag("POSSIBLE CANDIDATE"),
        important=sum(1 for c in cands if c.important),
        shortlisted=sum(1 for c in cands if c.shortlisted),
        deleted=sum(1 for c in cands if c.deleted),
        unprocessed=unprocessed,
        date_from=min(dates).strftime("%Y-%m-%d") if dates else None,
        date_to=max(dates).strftime("%Y-%m-%d") if dates else None,
    )
