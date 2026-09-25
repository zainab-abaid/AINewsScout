"""Role tokens, research-context admin APIs, and category deprecate."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_TOKEN, TEST_ANALYST_TOKEN


def test_viewer_cannot_patch_candidates(client: TestClient):
    c = client.get("/api/candidates?status=all").json()[0]
    bare = TestClient(client.app)
    res = bare.patch(f"/api/candidates/{c['id']}", json={"important": True})
    assert res.status_code == 403


def test_unlock_and_admin_research_context(client: TestClient):
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
    assert "probes" in body
    assert "artifacts" in body
    assert "not_useful" in body
    assert "prompt_preview" in body
    assert "Previous Genie probes" in body["prompt_preview"]

    created = bare.post(
        "/api/admin/priorities",
        headers=headers,
        json={"name": "Agents", "description": "Hands-on agent work"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["name"] == "Agents"

    # Analyst cannot edit research context.
    denied = bare.post(
        "/api/admin/priorities",
        headers={"X-Access-Token": TEST_ANALYST_TOKEN},
        json={"name": "Nope", "description": ""},
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

    still = bare.get("/api/candidates?status=all").json()[0]
    assert still["category_id"] == cat["id"]
    assert still["category_name"] == "Legacy topic"

    assert bare.post("/api/categories", headers=analyst, json={"name": "Nope"}).status_code == 403


def test_manual_probe_and_not_useful(client: TestClient):
    bare = TestClient(client.app)
    admin = {"X-Access-Token": TEST_ADMIN_TOKEN}
    probe = bare.post(
        "/api/admin/probes",
        headers=admin,
        json={"title": "Test probe", "description": "Two liner about a hands-on test."},
    )
    assert probe.status_code == 200, probe.text
    pid = probe.json()["id"]

    nu = bare.post(
        "/api/admin/not-useful",
        headers=admin,
        json={"text": "pure market gossip"},
    )
    assert nu.status_code == 200

    ctx = bare.get("/api/admin/research-context", headers=admin).json()
    assert any(p["id"] == pid for p in ctx["probes"])
    assert any(n["text"] == "pure market gossip" for n in ctx["not_useful"])
    assert "Test probe" in ctx["prompt_preview"]
    assert "pure market gossip" in ctx["prompt_preview"]
