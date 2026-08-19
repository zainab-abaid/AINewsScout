"""Re-importing email bodies with the current Markdown converter."""

from __future__ import annotations

import base64

import pytest
from sqlmodel import Session, select

import backend.services.gmail_sync as gmail_sync
from backend.db import Candidate, Email

HTML_BODY = """
<html><body>
<h2>Twitter recap</h2>
<ul>
  <li><strong>Small VLMs are getting serious</strong>: Cohere launched
      <a href="https://substack.com/redirect/601d390a">North Micro Vision</a>.</li>
  <li><strong>Infra releases</strong>: turbopuffer shipped sharding in beta.</li>
</ul>
<p>Closing paragraph.</p>
</body></html>
"""

# What the old plain-text import left behind: no blank lines, so it renders as
# one block.
PLAIN_ERA_BODY = (
    "# [AINews] Issue\n"
    "\n"
    "- **From:** AINews <swyx+ainews@substack.com>\n"
    "\n"
    "---\n"
    "\n"
    "Twitter recap\n"
    "Small VLMs are getting serious: Cohere launched North Micro Vision "
    "[ https://substack.com/redirect/601d390a ].\n"
    "Infra releases: turbopuffer shipped sharding in beta.\n"
    "Closing paragraph.\n"
)


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


class FakeMessages:
    def __init__(self, payloads: dict[str, dict], fail: set[str] | None = None):
        self.payloads = payloads
        self.fail = fail or set()
        self.fetched: list[str] = []

    def get(self, userId: str, id: str, format: str):  # noqa: N803 - Gmail's API spelling
        self.fetched.append(id)
        payloads, fail = self.payloads, self.fail

        class Req:
            def execute(self):
                if id in fail:
                    raise RuntimeError("Gmail is unhappy")
                return {"payload": payloads[id]}

        return Req()


class FakeService:
    def __init__(self, messages: FakeMessages):
        self._messages = messages

    def users(self):
        return self

    def messages(self):
        return self._messages


def payload_for(subject: str) -> dict:
    return {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "Subject", "value": subject},
            {"name": "From", "value": "AINews <swyx+ainews@substack.com>"},
            {"name": "To", "value": "reader@example.com"},
            {"name": "Date", "value": "Tue, 18 Aug 2026 09:00:00 +0000"},
            {"name": "Message-ID", "value": "<abc@mg1.substack.com>"},
        ],
        "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("plain fallback text")}},
            {"mimeType": "text/html", "body": {"data": b64(HTML_BODY)}},
        ],
    }


@pytest.fixture()
def stale_email(engine, monkeypatch):
    """An email stored by the plain-text era, with a mark on its candidate."""
    from backend.database import init_db

    init_db()
    with Session(engine) as session:
        email = Email(
            gmail_id="gmail-1",
            subject="[AINews] Issue",
            from_addr="AINews <swyx+ainews@substack.com>",
            date_raw="Tue, 18 Aug 2026 09:00:00 +0000",
            body_md=PLAIN_ERA_BODY,
            extraction_status="done",
        )
        session.add(email)
        session.commit()
        session.refresh(email)
        session.add(
            Candidate(
                email_id=email.id,
                tag="STRONG CANDIDATE",
                topic="Small VLMs",
                main_idea="Worth a probe.",
                excerpt="Cohere launched North Micro Vision.",
                important=True,
                notes="Keep an eye on this.",
            )
        )
        session.commit()

    messages = FakeMessages({"gmail-1": payload_for("[AINews] Issue")})
    monkeypatch.setattr(gmail_sync, "gmail_service", lambda: FakeService(messages))
    monkeypatch.setattr(gmail_sync, "get_label", lambda: "AINews")
    return messages


def stored_body(engine) -> str:
    with Session(engine) as session:
        return session.exec(select(Email)).one().body_md


def test_reimport_restores_structure_the_plain_text_era_lost(engine, stale_email):
    before = stored_body(engine)
    assert "## Twitter recap" not in before

    counts = gmail_sync.reimport_bodies()
    assert counts == {"checked": 1, "updated": 1, "unchanged": 0, "failed": 0}

    after = stored_body(engine)
    assert "## Twitter recap" in after
    assert "- **Small VLMs are getting serious**" in after
    assert "[North Micro Vision](https://substack.com/redirect/601d390a)" in after
    # Blank lines between blocks are what the reader splits on.
    assert after.count("\n\n") > before.count("\n\n")


def test_reimport_keeps_marks_comments_and_candidates(engine, stale_email):
    gmail_sync.reimport_bodies()
    with Session(engine) as session:
        cand = session.exec(select(Candidate)).one()
    assert cand.important is True
    assert cand.notes == "Keep an eye on this."
    assert cand.excerpt == "Cohere launched North Micro Vision."


def test_dry_run_reports_without_writing(engine, stale_email):
    before = stored_body(engine)
    lines: list[str] = []
    counts = gmail_sync.reimport_bodies(dry_run=True, report=lines.append)
    assert counts["updated"] == 1
    assert stored_body(engine) == before
    assert any("dry run" in line for line in lines)


def test_second_run_reports_nothing_to_do(engine, stale_email):
    gmail_sync.reimport_bodies()
    body = stored_body(engine)
    counts = gmail_sync.reimport_bodies()
    assert counts == {"checked": 1, "updated": 0, "unchanged": 1, "failed": 0}
    assert stored_body(engine) == body


def test_a_failed_fetch_leaves_the_old_body_alone(engine, stale_email, monkeypatch):
    before = stored_body(engine)
    messages = FakeMessages(
        {"gmail-1": payload_for("[AINews] Issue")}, fail={"gmail-1"}
    )
    monkeypatch.setattr(gmail_sync, "gmail_service", lambda: FakeService(messages))

    counts = gmail_sync.reimport_bodies()
    assert counts == {"checked": 1, "updated": 0, "unchanged": 0, "failed": 1}
    assert stored_body(engine) == before
