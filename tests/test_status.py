from __future__ import annotations

from backend.services.extract import openai_api_key
from backend.services.imap_sync import imap_status
from backend.services.jobs import get_active_job


def test_openai_key_comes_from_env(monkeypatch):
    monkeypatch.setattr("backend.services.extract.OPENAI_API_KEY", "sk-test-env")
    assert openai_api_key() == "sk-test-env"


def test_openai_key_missing(monkeypatch):
    monkeypatch.setattr("backend.services.extract.OPENAI_API_KEY", "")
    assert openai_api_key() == ""


def test_imap_status_reports_config(monkeypatch):
    monkeypatch.setattr("backend.services.imap_sync.IMAP_USER", "inbox@example.com")
    monkeypatch.setattr("backend.services.imap_sync.IMAP_PASSWORD", "app-pass")
    monkeypatch.setattr(
        "backend.services.imap_sync.IMAP_ALLOWED_FROM", ["you@example.com"]
    )
    monkeypatch.setattr("backend.services.imap_sync.IMAP_SYNC_ENABLED", True)
    monkeypatch.setattr("backend.services.imap_sync.IMAP_SYNC_HOUR", 6)
    status = imap_status()
    assert status["configured"] is True
    assert status["enabled"] is True
    assert status["user"] == "inbox@example.com"
    assert status["allowed_from"] == ["you@example.com"]


def test_imap_status_unconfigured_without_password(monkeypatch):
    monkeypatch.setattr("backend.services.imap_sync.IMAP_USER", "inbox@example.com")
    monkeypatch.setattr("backend.services.imap_sync.IMAP_PASSWORD", "")
    monkeypatch.setattr(
        "backend.services.imap_sync.IMAP_ALLOWED_FROM", ["you@example.com"]
    )
    status = imap_status()
    assert status["configured"] is False


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
