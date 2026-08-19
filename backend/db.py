from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Email(SQLModel, table=True):
    __tablename__ = "emails"

    id: Optional[int] = Field(default=None, primary_key=True)
    gmail_id: Optional[str] = Field(default=None, unique=True, index=True)
    rfc822_message_id: Optional[str] = Field(default=None, index=True)
    source_path: Optional[str] = None
    subject: str = ""
    from_addr: str = ""
    sent_at: Optional[datetime] = None
    date_raw: str = ""
    body_md: str = ""
    extraction_status: str = Field(default="pending", index=True)
    extraction_error: Optional[str] = None
    raw_model_response: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    is_default: bool = False
    sort_order: int = 0


class Candidate(SQLModel, table=True):
    __tablename__ = "candidates"

    id: Optional[int] = Field(default=None, primary_key=True)
    email_id: int = Field(foreign_key="emails.id", index=True)
    tag: str = Field(index=True)
    topic: str
    main_idea: str
    excerpt: str
    legacy_hash: Optional[str] = Field(default=None, unique=True, index=True)
    important: bool = False
    shortlisted: bool = False
    deleted: bool = False
    category_id: Optional[int] = Field(default=None, foreign_key="categories.id")
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    # When the item first became important or shortlisted; cleared if both are removed.
    marked_at: Optional[datetime] = None


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str
    status: str = Field(default="queued", index=True)
    payload_json: str = "{}"
    progress_json: str = "{}"
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None


class IdeaSearch(SQLModel, table=True):
    """One question asked across the stored emails in a date range."""

    __tablename__ = "idea_searches"

    id: Optional[int] = Field(default=None, primary_key=True)
    question: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    status: str = Field(default="queued", index=True)
    job_id: Optional[int] = None
    emails_total: int = 0
    chunks_total: int = 0
    chunks_done: int = 0
    chunks_failed: int = 0
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None


class IdeaSearchHit(SQLModel, table=True):
    """A passage the model considered relevant to a search question."""

    __tablename__ = "idea_search_hits"

    id: Optional[int] = Field(default=None, primary_key=True)
    search_id: int = Field(foreign_key="idea_searches.id", index=True)
    email_id: int = Field(foreign_key="emails.id", index=True)
    chunk_index: int = 0
    relevance: str = "related"
    title: str = ""
    excerpt: str = ""
    why_relevant: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    # Set when the user keeps this finding as a probe candidate.
    candidate_id: Optional[int] = Field(default=None, foreign_key="candidates.id", index=True)


class AppSetting(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str = ""
