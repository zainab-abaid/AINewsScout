"""Shared fixtures.

Every test runs against a temporary SQLite file so the local corpus is never
touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

import backend.database as database
from backend.db import Candidate, Email
from backend.routers.core import router as core_router
from backend.routers.search import router as search_router


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "probe_scout_test.sqlite"


@pytest.fixture()
def engine(db_path: Path):
    eng = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.engine = eng
    yield eng
    database.engine = None


@pytest.fixture()
def client(engine) -> TestClient:
    database.init_db()

    with Session(engine) as session:
        email = Email(
            gmail_id="test-1",
            subject="AINews test issue",
            from_addr="news@example.com",
            date_raw="Tue, 18 Aug 2026 09:00:00 +0000",
            body_md="# AINews test issue\n\nSome body text.",
            extraction_status="done",
        )
        session.add(email)
        session.commit()
        session.refresh(email)
        session.add(
            Candidate(
                email_id=email.id,
                tag="STRONG CANDIDATE",
                topic="Agent skills packaging",
                main_idea="Worth a probe.",
                excerpt="Verbatim excerpt.",
            )
        )
        session.commit()

    app = FastAPI()
    app.include_router(core_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    return TestClient(app)
