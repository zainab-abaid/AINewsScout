from __future__ import annotations

import json
from pathlib import Path

from backend.services.extract import openai_api_key
from backend.services.gmail_sync import gmail_status
from backend.services.jobs import get_active_job
from backend.secrets_store import load_gmail_client


def test_openai_key_comes_from_env(monkeypatch):
    monkeypatch.setattr("backend.services.extract.OPENAI_API_KEY", "sk-test-env")
    assert openai_api_key() == "sk-test-env"


def test_openai_key_missing(monkeypatch):
    monkeypatch.setattr("backend.services.extract.OPENAI_API_KEY", "")
    assert openai_api_key() == ""


def test_gmail_client_prefers_env(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("backend.secrets_store.GMAIL_CLIENT_ID", "env-id")
    monkeypatch.setattr("backend.secrets_store.GMAIL_CLIENT_SECRET", "env-secret")
    leftover = tmp_path / "gmail_oauth_client.json"
    leftover.write_text(json.dumps({"client_id": "file-id", "client_secret": "file-secret"}))
    monkeypatch.setattr("backend.secrets_store.GMAIL_CLIENT_PATH", leftover)
    client = load_gmail_client()
    assert client is not None
    assert client["client_id"] == "env-id"
    assert client["client_secret"] == "env-secret"


def test_gmail_client_falls_back_to_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("backend.secrets_store.GMAIL_CLIENT_ID", "")
    monkeypatch.setattr("backend.secrets_store.GMAIL_CLIENT_SECRET", "")
    leftover = tmp_path / "gmail_oauth_client.json"
    leftover.write_text(json.dumps({"client_id": "file-id", "client_secret": "file-secret"}))
    monkeypatch.setattr("backend.secrets_store.GMAIL_CLIENT_PATH", leftover)
    client = load_gmail_client()
    assert client is not None
    assert client["client_id"] == "file-id"


def test_gmail_status_is_local_only(monkeypatch):
    monkeypatch.setattr(
        "backend.services.gmail_sync.load_gmail_client",
        lambda: {"client_id": "id", "client_secret": "secret"},
    )
    monkeypatch.setattr(
        "backend.services.gmail_sync.load_gmail_token",
        lambda: {"refresh_token": "rt"},
    )
    monkeypatch.setattr("backend.services.gmail_sync.get_cached_email", lambda: "me@example.com")
    monkeypatch.setattr("backend.services.gmail_sync.get_label", lambda: "AINews")

    called = {"profile": False}

    def boom(*_a, **_k):
        called["profile"] = True
        raise AssertionError("status must not call Gmail")

    monkeypatch.setattr("backend.services.gmail_sync.build", boom)
    monkeypatch.setattr("backend.services.gmail_sync.credentials_from_store", boom)

    status = gmail_status()
    assert status["connected"] is True
    assert status["email"] == "me@example.com"
    assert status["has_client"] is True
    assert called["profile"] is False


def test_gmail_status_disconnected_without_token(monkeypatch):
    monkeypatch.setattr(
        "backend.services.gmail_sync.load_gmail_client",
        lambda: {"client_id": "id", "client_secret": "secret"},
    )
    monkeypatch.setattr("backend.services.gmail_sync.load_gmail_token", lambda: None)
    monkeypatch.setattr("backend.services.gmail_sync.get_cached_email", lambda: None)
    monkeypatch.setattr("backend.services.gmail_sync.get_label", lambda: "AINews")
    status = gmail_status()
    assert status["connected"] is False
    assert status["has_client"] is True


def test_active_job_none_when_empty(monkeypatch):
    class FakeSession:
        def exec(self, _stmt):
            return self

        def first(self):
            return None

    from contextlib import contextmanager

    @contextmanager
    def fake_scope():
        yield FakeSession()

    monkeypatch.setattr("backend.services.jobs.session_scope", fake_scope)
    assert get_active_job() is None
