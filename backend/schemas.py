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
    category: Optional[str] = None  # best-fit name from the supplied category list, or null


class ExtractionResult(BaseModel):
    candidates: list[ExtractedCandidate] = Field(default_factory=list)


class CategoryOut(BaseModel):
    id: int
    name: str
    is_default: bool
    sort_order: int
    deprecated: bool = False


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
    """Pull matching messages from the dedicated IMAP inbox, then extract."""

    extract: bool = True


class ExtractRequest(BaseModel):
    email_ids: Optional[list[int]] = None
    pending_only: bool = True


class CategoryCreate(BaseModel):
    name: str


class CategoryPatch(BaseModel):
    name: Optional[str] = None
    deprecated: Optional[bool] = None


class ResearchAreaIn(BaseModel):
    name: str
    description: str = ""


class ResearchItemOut(BaseModel):
    id: int
    title: str
    description: str = ""
    source_url: Optional[str] = None
    source_kind: str = "manual"
    sort_order: int = 0


class ResearchItemIn(BaseModel):
    title: str
    description: str = ""


class ResearchItemPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class ResearchPriorityOut(BaseModel):
    id: int
    name: str
    description: str = ""
    sort_order: int = 0


class ResearchPriorityIn(BaseModel):
    name: str
    description: str = ""


class ResearchPriorityPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ResearchNotUsefulOut(BaseModel):
    id: int
    text: str
    sort_order: int = 0


class ResearchNotUsefulIn(BaseModel):
    text: str


class ResearchContextOut(BaseModel):
    probes: list[ResearchItemOut] = Field(default_factory=list)
    artifacts: list[ResearchItemOut] = Field(default_factory=list)
    priority_areas: list[ResearchPriorityOut] = Field(default_factory=list)
    not_useful: list[ResearchNotUsefulOut] = Field(default_factory=list)
    source: str = "database"
    # Live preview of what the extractor currently receives as research context.
    prompt_preview: str = ""


class UrlIngestIn(BaseModel):
    url: str


class IngestPreviewOut(BaseModel):
    title: str
    description: str
    source_url: Optional[str] = None
    source_kind: str


class LlmLogSummaryOut(BaseModel):
    id: int
    kind: str
    email_id: Optional[int] = None
    model: str = ""
    created_at: str = ""
    input_preview: str = ""
    output_preview: str = ""


class LlmLogDetailOut(LlmLogSummaryOut):
    instructions_text: str = ""
    input_text: str = ""
    output_text: str = ""
    meta: dict = Field(default_factory=dict)


class AuthUnlockIn(BaseModel):
    token: str


class AuthStatusOut(BaseModel):
    role: str
    viewer_token_set: bool = False
    analyst_token_set: bool
    admin_token_set: bool


class Relevance(str, Enum):
    direct = "direct"
    related = "related"


class SearchFinding(BaseModel):
    """One relevant passage, as returned by the model for a chunk of emails."""

    email_id: int
    relevance: Relevance
    title: str
    excerpt: str
    why_relevant: str


class SearchFindings(BaseModel):
    findings: list[SearchFinding] = Field(default_factory=list)


class IdeaSearchCreate(BaseModel):
    question: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class SearchHitOut(BaseModel):
    id: int
    email_id: int
    relevance: str
    title: str
    excerpt: str
    why_relevant: str
    email_title: str = ""
    email_date: str = ""
    date_iso: str = ""
    candidate_id: Optional[int] = None


class KeepHitIn(BaseModel):
    tag: str
    category_id: Optional[int] = None
    notes: str = ""
    important: bool = True
    shortlisted: bool = False


class KeepHitOut(BaseModel):
    hit: SearchHitOut
    candidate: CandidateOut


class IdeaSearchOut(BaseModel):
    id: int
    question: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    status: str
    emails_total: int = 0
    chunks_total: int = 0
    chunks_done: int = 0
    chunks_failed: int = 0
    hits_total: int = 0
    error: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    phase: str = ""
    listed: int = 0
    new_emails: int = 0
    skipped: int = 0
    current: int = 0


class IdeaSearchDetailOut(IdeaSearchOut):
    hits: list[SearchHitOut] = Field(default_factory=list)


class SearchPreviewOut(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    emails: int = 0
    stored: int = 0
    will_fetch: int = 0
    inbox_configured: bool = False
    chunks: int = 0


def tag_slug(tag: str) -> str:
    return {
        "HIGH PRIORITY RESEARCH AREA": "high-priority",
        "STRONG CANDIDATE": "strong",
        "POSSIBLE CANDIDATE": "possible",
    }.get(tag, "possible")
