from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from enum import Enum


ALLOWED_TAGS = (
    "HIGH PRIORITY RESEARCH AREA",
    "STRONG CANDIDATE",
    "POSSIBLE CANDIDATE",
)

DEFAULT_CATEGORIES = [
    "Harness engineering & coding agents",
    "Enterprise control & shared AI resources",
    "Gateways & model routing",
    "Inference engineering",
    "Evaluation, observability & synthetic data",
    "Trace-driven improvement",
    "RAG, retrieval & agentic search",
    "Document processing & multimodal",
    "Memory & context engineering",
    "Guardrails, verification & reliability",
]


class Tag(str, Enum):
    high = "HIGH PRIORITY RESEARCH AREA"
    strong = "STRONG CANDIDATE"
    possible = "POSSIBLE CANDIDATE"


class ExtractedCandidate(BaseModel):
    tag: Tag
    topic: str
    main_idea: str
    excerpt: str


class ExtractionResult(BaseModel):
    candidates: list[ExtractedCandidate] = Field(default_factory=list)


class CategoryOut(BaseModel):
    id: int
    name: str
    is_default: bool
    sort_order: int


class CandidateOut(BaseModel):
    id: int
    email_id: int
    tag: str
    tag_slug: str
    topic: str
    main_idea: str
    excerpt: str
    important: bool
    shortlisted: bool
    deleted: bool
    processed: bool
    category_id: Optional[int] = None
    category_name: str = ""
    notes: str = ""
    marked_at: str = ""
    email_title: str = ""
    email_date: str = ""
    date_iso: str = ""
    from_addr: str = ""


class CandidatePatch(BaseModel):
    important: Optional[bool] = None
    shortlisted: Optional[bool] = None
    deleted: Optional[bool] = None
    category_id: Optional[int] = None
    clear_category: bool = False
    notes: Optional[str] = None


class EmailOut(BaseModel):
    id: int
    subject: str
    from_addr: str
    date_raw: str
    date_iso: str
    body_md: str
    extraction_status: str
    extraction_error: Optional[str] = None
    gmail_id: Optional[str] = None


class StatsOut(BaseModel):
    emails: int
    emails_with_candidates: int
    emails_pending_extraction: int
    candidates: int
    high_priority: int
    strong: int
    possible: int
    important: int
    shortlisted: int
    deleted: int
    unprocessed: int
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    payload: dict
    progress: dict
    error: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class SyncRequest(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    label: Optional[str] = None
    extract: bool = True
    overwrite_extracted: bool = False


class SyncPreviewOut(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    stored: int = 0
    extracted: int = 0
    pending: int = 0
    failed: int = 0
    candidates: int = 0
    marked: int = 0
    needs_confirm: bool = False


class ExtractRequest(BaseModel):
    email_ids: Optional[list[int]] = None
    pending_only: bool = True


class GmailClientIn(BaseModel):
    client_id: str
    client_secret: str


class CategoryCreate(BaseModel):
    name: str


def tag_slug(tag: str) -> str:
    return {
        "HIGH PRIORITY RESEARCH AREA": "high-priority",
        "STRONG CANDIDATE": "strong",
        "POSSIBLE CANDIDATE": "possible",
    }.get(tag, "possible")
