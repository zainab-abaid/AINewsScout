"""Checks for user marks: comments and the date an item was marked."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

import backend.database as database


def only_candidate(client: TestClient) -> dict:
    return client.get("/api/candidates?status=all").json()[0]


def test_marking_records_a_date_and_unmarking_clears_it(client: TestClient):
    c = only_candidate(client)
    assert c["marked_at"] == ""

    marked = client.patch(f"/api/candidates/{c['id']}", json={"important": True}).json()
    assert marked["important"] is True
    first_date = marked["marked_at"]
    assert first_date

    # A second mark on the same item keeps the original date.
    both = client.patch(f"/api/candidates/{c['id']}", json={"shortlisted": True}).json()
    assert both["marked_at"] == first_date

    # Dropping one mark keeps the item marked, so the date survives.
    one = client.patch(f"/api/candidates/{c['id']}", json={"important": False}).json()
    assert one["marked_at"] == first_date

    # Dropping the last mark clears it, so re-marking later gets a fresh date.
    none = client.patch(f"/api/candidates/{c['id']}", json={"shortlisted": False}).json()
    assert none["marked_at"] == ""


def test_comment_is_saved_edited_and_cleared(client: TestClient):
    c = only_candidate(client)
    assert c["notes"] == ""

    saved = client.patch(
        f"/api/candidates/{c['id']}",
        json={"important": True, "notes": "Ask about verifier loops."},
    ).json()
    assert saved["notes"] == "Ask about verifier loops."

    edited = client.patch(f"/api/candidates/{c['id']}", json={"notes": "Reframed."}).json()
    assert edited["notes"] == "Reframed."
    # Editing a comment must not move the date the item was marked.
    assert edited["marked_at"] == saved["marked_at"]

    cleared = client.patch(f"/api/candidates/{c['id']}", json={"notes": ""}).json()
    assert cleared["notes"] == ""

    # Comments survive a reload.
    assert only_candidate(client)["notes"] == ""


def test_database_from_an_earlier_version_gains_the_marked_at_column(
    engine, db_path: Path
):
    if sqlite3.sqlite_version_info < (3, 35):
        pytest.skip("DROP COLUMN needs SQLite 3.35+ to simulate the old schema")

    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE candidates DROP COLUMN marked_at")
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(candidates)")}
    assert "marked_at" not in cols
    assert db_path.exists()

    database.init_db()

    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(candidates)")}
    assert "marked_at" in cols
    # The upgraded database is queryable, not just structurally correct.
    with Session(engine) as session:
        session.exec(SQLModel.metadata.tables["candidates"].select())


def test_items_marked_before_the_upgrade_fall_back_to_the_extraction_date(
    client: TestClient, engine
):
    c = only_candidate(client)
    # Simulate a mark made by an older version, which recorded no date.
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE candidates SET important = 1, marked_at = NULL WHERE id = ?",
            (c["id"],),
        )
    assert only_candidate(client)["marked_at"] == ""

    database.init_db()
    backfilled = only_candidate(client)
    with engine.begin() as conn:
        created_at = conn.exec_driver_sql(
            "SELECT created_at FROM candidates WHERE id = ?", (c["id"],)
        ).scalar_one()
    assert backfilled["marked_at"][:10] == str(created_at)[:10]

    # Running again leaves the backfilled date alone.
    database.init_db()
    assert only_candidate(client)["marked_at"] == backfilled["marked_at"]
