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


class AppSetting(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str = ""
