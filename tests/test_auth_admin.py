"""Role tokens, research-context admin saves, and category deprecate."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_TOKEN, TEST_ANALYST_TOKEN


def test_viewer_cannot_patch_candidates(client: TestClient):
    c = client.get("/api/candidates?status=all").json()[0]
    res = client.patch(
        f"/api/candidates/{c['id']}",
        json={"important": True},
        headers={"X-Access-Token": ""},
    )
    # Empty header still sends analyst from fixture default — override by
    # rebuilding request without the fixture header.
    bare = TestClient(client.app)
    res = bare.patch(f"/api/candidates/{c['id']}", json={"important": True})
    assert res.status_code == 403


def test_unlock_and_admin_research_context(client: TestClient, monkeypatch):
    bare = TestClient(client.app)
    status = bare.get("/api/auth/status").json()
    assert status["role"] == "viewer"
    assert status["analyst_token_set"] is True
    assert status["admin_token_set"] is True

    bad = bare.post("/api/auth/unlock", json={"token": "nope"})
    assert bad.status_code == 401

    unlocked = bare.post("/api/auth/unlock", json={"token": TEST_ADMIN_TOKEN}).json()
    assert unlocked["role"] == "admin"

    headers = {"X-Access-Token": TEST_ADMIN_TOKEN}
    ctx = bare.get("/api/admin/research-context", headers=headers)
    assert ctx.status_code == 200
    body = ctx.json()
    assert "priority_areas" in body
    assert "past_probes" in body
    assert "not_useful" in body

    saved = bare.put(
        "/api/admin/research-context",
        headers=headers,
        json={
            "priority_areas": [{"name": "Agents", "description": "Hands-on agent work"}],
            "past_probes": [{"name": "RAG probe", "description": "Done"}],
            "not_useful": ["marketing fluff"],
        },
    )
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data["source"] == "database"
    assert data["priority_areas"][0]["name"] == "Agents"

    again = bare.get("/api/admin/research-context", headers=headers).json()
    assert again["source"] == "database"
    assert again["not_useful"] == ["marketing fluff"]

    # Analyst cannot edit research context.
    denied = bare.put(
        "/api/admin/research-context",
        headers={"X-Access-Token": TEST_ANALYST_TOKEN},
        json={"priority_areas": [], "past_probes": [], "not_useful": []},
    )
    assert denied.status_code == 403


def test_category_deprecate_keeps_assignment(client: TestClient):
    bare = TestClient(client.app)
    admin = {"X-Access-Token": TEST_ADMIN_TOKEN}
    analyst = {"X-Access-Token": TEST_ANALYST_TOKEN}

    cat = bare.post("/api/categories", headers=admin, json={"name": "Legacy topic"}).json()
    candidate = bare.get("/api/candidates?status=all").json()[0]
    patched = bare.patch(
        f"/api/candidates/{candidate['id']}",
        headers=analyst,
        json={"category_id": cat["id"]},
    ).json()
    assert patched["category_name"] == "Legacy topic"

    dep = bare.patch(
        f"/api/categories/{cat['id']}",
        headers=admin,
        json={"deprecated": True},
    )
    assert dep.status_code == 200
    assert dep.json()["deprecated"] is True

    # Old assignment survives deprecate.
    still = bare.get("/api/candidates?status=all").json()[0]
    assert still["category_id"] == cat["id"]
    assert still["category_name"] == "Legacy topic"

    # Creating categories requires admin.
    assert bare.post("/api/categories", headers=analyst, json={"name": "Nope"}).status_code == 403
