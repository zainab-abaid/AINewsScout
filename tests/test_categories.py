"""End-to-end checks for creating a category and assigning it to a candidate.

Runs against a temporary SQLite file so the local corpus is never touched.
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


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'probe_scout_test.sqlite'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.engine = engine
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
    return TestClient(app)


def test_new_category_is_created_assigned_and_persisted(client: TestClient):
    before = client.get("/api/categories").json()
    assert all(c["name"] != "Agent skills" for c in before)

    created = client.post("/api/categories", json={"name": "Agent skills"})
    assert created.status_code == 200, created.text
    cat = created.json()
    assert cat["id"]
    assert cat["name"] == "Agent skills"
    assert cat["is_default"] is False

    # Immediately listed, so the dropdown picks it up without a reload.
    listed = client.get("/api/categories").json()
    assert any(c["id"] == cat["id"] for c in listed)

    # Creating the same name again reuses the row instead of duplicating it.
    again = client.post("/api/categories", json={"name": "Agent skills"}).json()
    assert again["id"] == cat["id"]
    assert len(client.get("/api/categories").json()) == len(listed)

    candidate = client.get("/api/candidates?status=all").json()[0]
    patched = client.patch(
        f"/api/candidates/{candidate['id']}", json={"category_id": cat["id"]}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["category_id"] == cat["id"]
    assert patched.json()["category_name"] == "Agent skills"

    # The candidate is still returned by the list endpoint after assignment.
    rows = client.get("/api/candidates?status=all").json()
    assert [r["id"] for r in rows] == [candidate["id"]]
    assert rows[0]["category_id"] == cat["id"]

    # Assigning a category must not mark the item as processed.
    assert rows[0]["processed"] is False
    assert client.get("/api/candidates?status=unprocessed").json()[0]["id"] == candidate["id"]


def test_blank_category_name_is_rejected(client: TestClient):
    assert client.post("/api/categories", json={"name": "   "}).status_code == 400


def test_category_can_be_cleared(client: TestClient):
    cat = client.post("/api/categories", json={"name": "Temp"}).json()
    candidate = client.get("/api/candidates?status=all").json()[0]
    client.patch(f"/api/candidates/{candidate['id']}", json={"category_id": cat["id"]})
    cleared = client.patch(
        f"/api/candidates/{candidate['id']}", json={"clear_category": True}
    ).json()
    assert cleared["category_id"] is None
    assert cleared["category_name"] == ""
