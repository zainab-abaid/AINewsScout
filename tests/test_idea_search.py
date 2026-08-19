"""Idea search: batching emails, prompting, validating findings, and the job."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlmodel import Session, select

import backend.database as database
import backend.routers.search as search_router_module
import backend.services.jobs as jobs
from backend.database import init_db
from backend.db import Candidate, Email, IdeaSearch, IdeaSearchHit, Job
from backend.schemas import Relevance, SearchFinding
from backend.services.idea_search import (
    SearchEmail,
    build_chunk_input,
    chunk_emails,
    clean_findings,
    excerpts_match,
    normalize_excerpt,
    readable_model_error,
)


def email(eid: int, size: int = 100, subject: str = "", body: str = "") -> SearchEmail:
    return SearchEmail(
        id=eid,
        subject=subject or f"[AINews] Issue {eid}",
        date=f"2026-08-{eid:02d}",
        body_md=body or ("x" * size),
    )


class TestChunking:
    def test_packs_up_to_the_email_limit(self):
        chunks = chunk_emails([email(i) for i in range(1, 10)], per_chunk=4)
        assert [len(c) for c in chunks] == [4, 4, 1]

    def test_keeps_the_corpus_order_and_loses_nothing(self):
        emails = [email(i) for i in range(1, 8)]
        chunks = chunk_emails(emails, per_chunk=3)
        flat = [e.id for chunk in chunks for e in chunk]
        assert flat == [e.id for e in emails]

    def test_closes_a_batch_early_when_it_would_exceed_the_char_budget(self):
        # Three 60k emails fit the count limit but not a 150k budget.
        emails = [email(i, size=60_000) for i in range(1, 4)]
        chunks = chunk_emails(emails, per_chunk=4, char_budget=150_000)
        assert [len(c) for c in chunks] == [2, 1]

    def test_an_oversized_email_is_sent_alone_rather_than_dropped(self):
        emails = [email(1, size=10), email(2, size=500_000), email(3, size=10)]
        chunks = chunk_emails(emails, per_chunk=4, char_budget=100_000)
        assert [[e.id for e in c] for c in chunks] == [[1], [2], [3]]

    def test_no_emails_means_no_batches(self):
        assert chunk_emails([]) == []


class TestPrompt:
    def test_carries_the_question_and_marks_every_email(self):
        chunk = [email(7, body="Harness choice changed the score."), email(9)]
        text = build_chunk_input("  which studies mention harnesses?  ", chunk)

        assert "which studies mention harnesses?" in text
        assert "USER QUESTION:" in text
        assert "EMAIL BATCH (2 email(s)):" in text
        # The model attributes findings by these ids, so each must be present
        # with its date and subject.
        assert "===== EMAIL id=7 | date=2026-08-07 | subject=[AINews] Issue 7 =====" in text
        assert "===== EMAIL id=9 | date=2026-08-09 | subject=[AINews] Issue 9 =====" in text
        assert "Harness choice changed the score." in text

    def test_email_order_in_the_prompt_matches_the_batch(self):
        text = build_chunk_input("q", [email(4), email(2)])
        assert text.index("id=4") < text.index("id=2")


def finding(email_id: int, excerpt: str = "A real quote.", **kw) -> SearchFinding:
    return SearchFinding(
        email_id=email_id,
        relevance=kw.get("relevance", Relevance.direct),
        title=kw.get("title", "Title"),
        excerpt=excerpt,
        why_relevant=kw.get("why_relevant", "Because."),
    )


class TestCleanFindings:
    def test_drops_a_finding_pointing_at_an_email_outside_the_batch(self):
        chunk = [email(1)]
        kept = clean_findings([finding(1), finding(99)], chunk)
        assert [f.email_id for f in kept] == [1]

    def test_drops_a_finding_with_no_quote(self):
        chunk = [email(1)]
        kept = clean_findings([finding(1, excerpt="   ")], chunk)
        assert kept == []

    def test_trims_the_title_and_commentary(self):
        chunk = [email(1)]
        kept = clean_findings(
            [finding(1, title="  Padded  ", why_relevant="  Spaced.  ")], chunk
        )
        assert kept[0].title == "Padded"
        assert kept[0].why_relevant == "Spaced."

    def test_restores_a_link_the_model_dropped_from_the_quote(self):
        body = (
            "Harness choice is now a first-order variable: a "
            "[SWE-bench Pro run](https://example.com/paper) showed a 12 point spread.\n"
        )
        chunk = [email(1, body=body)]
        kept = clean_findings(
            [
                finding(
                    1,
                    excerpt=(
                        "Harness choice is now a first-order variable: a "
                        "SWE-bench Pro run showed a 12 point spread."
                    ),
                )
            ],
            chunk,
        )
        assert "https://example.com/paper" in kept[0].excerpt


class TestExcerptMatch:
    def test_treats_a_link_and_its_visible_text_as_the_same_quote(self):
        with_link = "See the [SWE-bench Pro run](https://example.com/paper) result."
        without = "See the SWE-bench Pro run result."
        assert excerpts_match(with_link, without)

    def test_a_shorter_cut_of_the_same_passage_still_matches(self):
        full = (
            "Harness choice is now a first-order variable: a SWE-bench Pro run "
            "showed a 12 point spread across otherwise identical models."
        )
        cut = "Harness choice is now a first-order variable: a SWE-bench Pro run showed a 12 point spread"
        assert excerpts_match(full, cut)

    def test_unrelated_passages_do_not_match(self):
        assert not excerpts_match(
            "Harness choice moved SWE-bench scores by 12 points.",
            "Gemini 3.7 Flash brings GDM back to the frontier.",
        )

    def test_empty_quotes_never_match(self):
        assert not excerpts_match("", "anything at all here that is long enough")
        assert normalize_excerpt("[x](https://e.com)") == "x"


@pytest.fixture(autouse=True)
def no_live_gmail(monkeypatch):
    """These tests must not list or download from the real mailbox."""
    monkeypatch.setattr(jobs, "_gmail_connected", lambda: False)
    monkeypatch.setattr(jobs, "missing_gmail_count", lambda *_a, **_k: 0)


class TestReadableModelError:
    def test_pulls_the_message_out_of_an_api_error_body(self):
        exc = RuntimeError("Error code: 429 - {...}")
        exc.body = {  # type: ignore[attr-defined]
            "error": {
                "message": "You have no credits remaining.",
                "code": "credit_balance_exhausted",
            }
        }
        assert readable_model_error(exc) == "You have no credits remaining."

    def test_falls_back_to_the_message_inside_the_stringified_error(self):
        exc = RuntimeError(
            "Error code: 429 - {'error': {'message': 'Rate limit reached', 'type': 'x'}}"
        )
        assert readable_model_error(exc) == "Rate limit reached"

    def test_keeps_a_plain_error_as_written(self):
        assert readable_model_error(RuntimeError("Connection reset")) == "Connection reset"


@pytest.fixture()
def corpus(engine):
    """Five stored emails on consecutive days, oldest first."""
    init_db()
    with Session(engine) as session:
        for day in range(15, 20):
            session.add(
                Email(
                    gmail_id=f"g-{day}",
                    subject=f"[AINews] Aug {day}",
                    from_addr="news@example.com",
                    date_raw=f"Wed, {day} Aug 2026 09:00:00 +0000",
                    sent_at=datetime(2026, 8, day),
                    body_md=f"Body for Aug {day}. Harness choice moved scores.",
                    extraction_status="done",
                )
            )
        session.commit()
    with Session(engine) as session:
        rows = session.exec(
            select(Email).where(Email.gmail_id.like("g-%")).order_by(Email.id)
        ).all()
        return [e.id for e in rows]


def start_search(question: str = "which studies link harnesses to scores?", **kw) -> int:
    with Session(database.get_engine()) as session:
        search = IdeaSearch(question=question, **kw)
        session.add(search)
        session.commit()
        session.refresh(search)
        return search.id


def run_search(search_id: int) -> Job:
    job = jobs.create_job("idea_search", {"search_id": search_id})
    jobs.run_idea_search_job(job.id)
    with Session(database.get_engine()) as session:
        return session.get(Job, job.id)


def read_search(search_id: int) -> IdeaSearch:
    with Session(database.get_engine()) as session:
        return session.get(IdeaSearch, search_id)


def read_hits(search_id: int) -> list[IdeaSearchHit]:
    with Session(database.get_engine()) as session:
        return list(
            session.exec(
                select(IdeaSearchHit)
                .where(IdeaSearchHit.search_id == search_id)
                .order_by(IdeaSearchHit.id)
            ).all()
        )


class TestSearchJob:
    def test_searches_every_batch_and_stores_what_it_finds(self, corpus, monkeypatch):
        seen: list[list[int]] = []

        def fake_search(question, chunk):
            seen.append([e.id for e in chunk])
            return [finding(chunk[0].id, excerpt=f"Quote from {chunk[0].id}.")]

        monkeypatch.setattr(jobs, "search_chunk", fake_search)
        monkeypatch.setattr(jobs, "chunk_emails", lambda emails: chunk_emails(emails, 2))

        search_id = start_search()
        job = run_search(search_id)

        # Five emails in batches of two: three calls, corpus order preserved.
        assert seen == [corpus[0:2], corpus[2:4], corpus[4:5]]
        assert job.status == "done"

        search = read_search(search_id)
        assert search.status == "done"
        assert (search.emails_total, search.chunks_total) == (5, 3)
        assert search.chunks_done == 3
        assert search.chunks_failed == 0
        assert search.finished_at is not None

        hits = read_hits(search_id)
        assert [h.excerpt for h in hits] == [
            f"Quote from {corpus[0]}.",
            f"Quote from {corpus[2]}.",
            f"Quote from {corpus[4]}.",
        ]
        assert [h.chunk_index for h in hits] == [0, 1, 2]

    def test_only_searches_emails_inside_the_date_range(self, corpus, monkeypatch):
        seen: list[int] = []

        def fake_search(question, chunk):
            seen.extend(e.id for e in chunk)
            return []

        monkeypatch.setattr(jobs, "search_chunk", fake_search)
        search_id = start_search(date_from="2026-08-17", date_to="2026-08-18")
        run_search(search_id)

        assert seen == corpus[2:4]
        assert read_search(search_id).emails_total == 2

    def test_one_failing_batch_keeps_the_rest_of_the_evidence(self, corpus, monkeypatch):
        def fake_search(question, chunk):
            if chunk[0].id == corpus[2]:
                raise RuntimeError("model timed out")
            return [finding(chunk[0].id)]

        monkeypatch.setattr(jobs, "search_chunk", fake_search)
        monkeypatch.setattr(jobs, "chunk_emails", lambda emails: chunk_emails(emails, 2))

        search_id = start_search()
        job = run_search(search_id)

        assert job.status == "done"
        search = read_search(search_id)
        assert search.status == "done"
        assert search.chunks_failed == 1
        assert search.error and "timed out" in search.error
        assert len(read_hits(search_id)) == 2

    def test_a_search_that_fails_everywhere_is_marked_failed(self, corpus, monkeypatch):
        def boom(question, chunk):
            raise RuntimeError("no api key")

        monkeypatch.setattr(jobs, "search_chunk", boom)
        search_id = start_search()
        job = run_search(search_id)

        assert job.status == "failed"
        search = read_search(search_id)
        assert search.status == "failed"
        assert "no api key" in search.error
        assert read_hits(search_id) == []

    def test_rerunning_a_search_replaces_its_earlier_hits(self, corpus, monkeypatch):
        monkeypatch.setattr(
            jobs, "search_chunk", lambda q, chunk: [finding(chunk[0].id)]
        )
        monkeypatch.setattr(jobs, "chunk_emails", lambda emails: chunk_emails(emails, 5))

        search_id = start_search()
        run_search(search_id)
        first = len(read_hits(search_id))
        # A restart resumes the job, which starts the batches again.
        run_search(search_id)

        assert first == 1
        assert len(read_hits(search_id)) == 1

    def test_deleting_a_search_mid_run_stops_it_without_orphan_hits(
        self, corpus, monkeypatch
    ):
        calls: list[int] = []

        def fake_search(question, chunk):
            calls.append(chunk[0].id)
            # Standing in for the user deleting the search from the UI while the
            # first batch was still with the model.
            with Session(database.get_engine()) as session:
                search = session.get(IdeaSearch, search_id)
                if search:
                    session.delete(search)
                    session.commit()
            return [finding(chunk[0].id)]

        monkeypatch.setattr(jobs, "search_chunk", fake_search)
        monkeypatch.setattr(jobs, "chunk_emails", lambda emails: chunk_emails(emails, 2))

        search_id = start_search()
        job = run_search(search_id)

        assert len(calls) == 1  # no further batches were paid for
        assert job.status == "done"
        assert json.loads(job.progress_json)["phase"] == "cancelled"
        assert read_hits(search_id) == []

    def test_a_missing_search_record_fails_the_job_cleanly(self, corpus):
        job = jobs.create_job("idea_search", {"search_id": 9999})
        jobs.run_idea_search_job(job.id)
        with Session(database.get_engine()) as session:
            assert session.get(Job, job.id).status == "failed"


class TestSearchPullsMissingEmails:
    def test_preview_counts_missing_gmail_messages(self, client, corpus, monkeypatch):
        monkeypatch.setattr(jobs, "_gmail_connected", lambda: True)
        monkeypatch.setattr(jobs, "missing_gmail_count", lambda *_a, **_k: 2)
        resp = client.post(
            "/api/searches/preview",
            json={"question": "ignored", "date_from": "2026-07-20", "date_to": "2026-08-19"},
        )
        body = resp.json()
        assert body["stored"] == 5
        assert body["will_fetch"] == 2
        assert body["emails"] == 7
        assert body["gmail_connected"] is True
        assert body["chunks"] == 2  # 7 emails, 4 per batch

    def test_starts_a_search_when_the_range_is_only_in_gmail(
        self, client, corpus, monkeypatch
    ):
        monkeypatch.setattr(search_router_module, "openai_api_key", lambda: "sk-test")
        monkeypatch.setattr(
            search_router_module, "run_idea_search_job", lambda job_id: None
        )
        monkeypatch.setattr(jobs, "_gmail_connected", lambda: True)
        monkeypatch.setattr(jobs, "missing_gmail_count", lambda *_a, **_k: 1)
        resp = client.post(
            "/api/searches",
            json={
                "question": "harnesses?",
                "date_from": "2020-01-01",
                "date_to": "2020-01-02",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["emails_total"] == 1

    def test_still_rejects_an_empty_range_when_gmail_has_nothing_either(
        self, client, corpus, monkeypatch
    ):
        monkeypatch.setattr(search_router_module, "openai_api_key", lambda: "sk-test")
        monkeypatch.setattr(jobs, "_gmail_connected", lambda: True)
        monkeypatch.setattr(jobs, "missing_gmail_count", lambda *_a, **_k: 0)
        resp = client.post(
            "/api/searches",
            json={
                "question": "harnesses?",
                "date_from": "2020-01-01",
                "date_to": "2020-01-02",
            },
        )
        assert resp.status_code == 400
        assert "gmail" in resp.json()["detail"].lower()

    def test_fetches_missing_emails_then_searches_them(self, corpus, monkeypatch):
        fetched_ranges: list[tuple] = []
        seen: list[int] = []

        def fake_fetch(date_from, date_to, label, progress):
            fetched_ranges.append((date_from, date_to, label))
            progress({"phase": "fetching", "listed": 1, "new_emails": 1, "skipped": 5})
            with Session(database.get_engine()) as session:
                session.add(
                    Email(
                        gmail_id="g-new",
                        subject="[AINews] newly pulled",
                        from_addr="news@example.com",
                        date_raw="Mon, 20 Jul 2026 09:00:00 +0000",
                        sent_at=datetime(2026, 7, 20),
                        body_md="Harness choice moved scores in July.",
                        extraction_status="pending",
                    )
                )
                session.commit()
            return {"listed": 1, "new_emails": 1, "skipped": 5}, [99]

        monkeypatch.setattr(jobs, "_gmail_connected", lambda: True)
        monkeypatch.setattr(jobs, "fetch_and_store", fake_fetch)
        monkeypatch.setattr(
            jobs, "search_chunk", lambda q, chunk: seen.extend(e.id for e in chunk) or []
        )

        search_id = start_search(date_from="2026-07-20", date_to="2026-08-19")
        job = run_search(search_id)

        assert fetched_ranges[0][0].isoformat() == "2026-07-20"
        assert fetched_ranges[0][1].isoformat() == "2026-08-19"
        assert job.status == "done"
        assert json.loads(job.progress_json)["new_emails"] == 1
        assert json.loads(job.progress_json)["skipped"] == 5
        search = read_search(search_id)
        assert search.emails_total == 6
        with Session(database.get_engine()) as session:
            extra = session.exec(select(Email).where(Email.gmail_id == "g-new")).first()
            assert extra is not None
            assert extra.id in seen
            assert extra.extraction_status == "pending"

    def test_does_not_call_gmail_when_disconnected(self, corpus, monkeypatch):
        calls: list[str] = []

        def boom(*_a, **_k):
            calls.append("fetch")
            raise AssertionError("must not download when Gmail is disconnected")

        monkeypatch.setattr(jobs, "fetch_and_store", boom)
        monkeypatch.setattr(jobs, "search_chunk", lambda q, chunk: [])
        run_search(start_search())
        assert calls == []

    def test_skips_gmail_ids_already_stored(self, corpus, monkeypatch):
        skipped = {"n": 0}

        def fake_fetch(date_from, date_to, label, progress):
            skipped["n"] += 5
            progress({"phase": "fetched", "listed": 5, "new_emails": 0, "skipped": 5})
            return {"listed": 5, "new_emails": 0, "skipped": 5}, []

        monkeypatch.setattr(jobs, "_gmail_connected", lambda: True)
        monkeypatch.setattr(jobs, "fetch_and_store", fake_fetch)
        monkeypatch.setattr(jobs, "search_chunk", lambda q, chunk: [])
        search_id = start_search()
        run_search(search_id)
        assert skipped["n"] == 5
        assert read_search(search_id).emails_total == 5


class TestSearchApi:
    @pytest.fixture(autouse=True)
    def stub_model(self, monkeypatch):
        monkeypatch.setattr(search_router_module, "openai_api_key", lambda: "sk-test")
        monkeypatch.setattr(
            search_router_module, "run_idea_search_job", lambda job_id: None
        )

    def test_rejects_a_blank_question(self, client, corpus):
        resp = client.post("/api/searches", json={"question": "   "})
        assert resp.status_code == 400
        assert "question" in resp.json()["detail"].lower()

    def test_rejects_a_range_with_no_stored_emails(self, client, corpus):
        resp = client.post(
            "/api/searches",
            json={"question": "harnesses?", "date_from": "2020-01-01", "date_to": "2020-01-02"},
        )
        assert resp.status_code == 400
        assert "connect gmail" in resp.json()["detail"].lower()

    def test_rejects_a_search_with_no_api_key(self, client, corpus, monkeypatch):
        monkeypatch.setattr(search_router_module, "openai_api_key", lambda: "")
        resp = client.post("/api/searches", json={"question": "harnesses?"})
        assert resp.status_code == 400
        assert "OPENAI_API_KEY" in resp.json()["detail"]

    def test_creates_a_search_and_reports_the_work_ahead(self, client, corpus):
        resp = client.post(
            "/api/searches", json={"question": "  which studies link harnesses?  "}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["question"] == "which studies link harnesses?"
        assert body["status"] == "queued"
        assert body["emails_total"] == 5
        assert body["chunks_total"] == 2  # five emails, four per batch
        assert body["hits_total"] == 0

        listed = client.get("/api/searches").json()
        assert [s["id"] for s in listed] == [body["id"]]

    def test_preview_counts_emails_and_batches_without_starting_anything(
        self, client, corpus
    ):
        resp = client.post(
            "/api/searches/preview",
            json={"question": "ignored", "date_from": "2026-08-15", "date_to": "2026-08-17"},
        )
        assert resp.json() == {
            "date_from": "2026-08-15",
            "date_to": "2026-08-17",
            "emails": 3,
            "stored": 3,
            "will_fetch": 0,
            "gmail_connected": False,
            "gmail_checked": False,
            "chunks": 1,
        }
        assert client.get("/api/searches").json() == []

    def test_results_put_direct_answers_first_then_newest_email(self, client, corpus):
        search_id = start_search()
        with Session(database.get_engine()) as session:
            session.add_all(
                [
                    IdeaSearchHit(
                        search_id=search_id,
                        email_id=corpus[0],
                        relevance="related",
                        title="Older related",
                        excerpt="Related quote.",
                        why_relevant="Context only.",
                    ),
                    IdeaSearchHit(
                        search_id=search_id,
                        email_id=corpus[1],
                        relevance="direct",
                        title="Older direct",
                        excerpt="Direct quote.",
                        why_relevant="Answers it.",
                    ),
                    IdeaSearchHit(
                        search_id=search_id,
                        email_id=corpus[4],
                        relevance="direct",
                        title="Newest direct",
                        excerpt="Newest quote.",
                        why_relevant="Answers it too.",
                    ),
                ]
            )
            session.commit()

        body = client.get(f"/api/searches/{search_id}").json()
        assert [h["title"] for h in body["hits"]] == [
            "Newest direct",
            "Older direct",
            "Older related",
        ]
        assert body["hits_total"] == 3
        # Each hit carries what the UI needs to link back to the newsletter.
        first = body["hits"][0]
        assert first["email_id"] == corpus[4]
        assert first["email_title"] == "[AINews] Aug 19"
        assert first["date_iso"] == "2026-08-19"

    def test_unknown_search_is_a_404(self, client, corpus):
        assert client.get("/api/searches/4242").status_code == 404
        assert client.delete("/api/searches/4242").status_code == 404

    def test_deleting_a_search_removes_its_hits(self, client, corpus):
        search_id = start_search()
        with Session(database.get_engine()) as session:
            session.add(
                IdeaSearchHit(
                    search_id=search_id,
                    email_id=corpus[0],
                    excerpt="Quote.",
                    title="T",
                    why_relevant="W",
                )
            )
            session.commit()

        assert client.delete(f"/api/searches/{search_id}").status_code == 200
        assert client.get(f"/api/searches/{search_id}").status_code == 404
        assert read_hits(search_id) == []


def _add_hit(search_id: int, email_id: int, **kw) -> int:
    with Session(database.get_engine()) as session:
        hit = IdeaSearchHit(
            search_id=search_id,
            email_id=email_id,
            title=kw.get("title", "Harness paper"),
            excerpt=kw.get(
                "excerpt",
                "Harness choice moved SWE-bench scores by 12 points.",
            ),
            why_relevant=kw.get("why_relevant", "It reports a measured harness effect."),
        )
        session.add(hit)
        session.commit()
        session.refresh(hit)
        return hit.id


class TestKeepHit:
    def _category_id(self, client) -> int:
        return client.get("/api/categories").json()[0]["id"]

    def test_keep_creates_a_marked_candidate(self, client, corpus):
        search_id = start_search()
        hid = _add_hit(search_id, corpus[0])
        cat = self._category_id(client)
        resp = client.post(
            f"/api/searches/{search_id}/hits/{hid}/keep",
            json={
                "tag": "STRONG CANDIDATE",
                "category_id": cat,
                "notes": "Worth a probe on SWE-bench.",
                "important": True,
                "shortlisted": False,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cand = body["candidate"]
        assert cand["tag"] == "STRONG CANDIDATE"
        assert cand["tag_slug"] == "strong"
        assert cand["topic"] == "Harness paper"
        assert cand["important"] is True
        assert cand["shortlisted"] is False
        assert cand["processed"] is True
        assert cand["category_id"] == cat
        assert cand["notes"] == "Worth a probe on SWE-bench."
        assert cand["marked_at"]
        assert cand["email_id"] == corpus[0]
        assert body["hit"]["candidate_id"] == cand["id"]

        listed = client.get("/api/candidates?status=all").json()
        assert any(c["id"] == cand["id"] for c in listed)
        marked = client.get("/api/candidates?status=important").json()
        assert any(c["id"] == cand["id"] for c in marked)

    def test_keep_again_updates_the_same_candidate(self, client, corpus):
        search_id = start_search()
        hid = _add_hit(search_id, corpus[0])
        cat = self._category_id(client)
        first = client.post(
            f"/api/searches/{search_id}/hits/{hid}/keep",
            json={"tag": "POSSIBLE CANDIDATE", "category_id": cat, "important": True},
        ).json()["candidate"]["id"]
        second = client.post(
            f"/api/searches/{search_id}/hits/{hid}/keep",
            json={
                "tag": "HIGH PRIORITY RESEARCH AREA",
                "category_id": cat,
                "notes": "Upgraded.",
                "important": True,
                "shortlisted": True,
            },
        ).json()
        assert second["candidate"]["id"] == first
        assert second["candidate"]["tag_slug"] == "high-priority"
        assert second["candidate"]["shortlisted"] is True
        assert second["candidate"]["notes"] == "Upgraded."
        with Session(database.get_engine()) as session:
            n = len(
                session.exec(select(Candidate).where(Candidate.email_id == corpus[0])).all()
            )
        # The client fixture already has one candidate on a different email.
        assert n == 1

    def test_keep_merges_into_an_existing_extracted_candidate(self, client, corpus):
        with Session(database.get_engine()) as session:
            session.add(
                Candidate(
                    email_id=corpus[0],
                    tag="POSSIBLE CANDIDATE",
                    topic="Existing extraction",
                    main_idea="Already pulled out.",
                    excerpt="Harness choice moved SWE-bench scores by 12 points.",
                )
            )
            session.commit()
        search_id = start_search()
        hid = _add_hit(
            search_id,
            corpus[0],
            excerpt="Harness choice moved SWE-bench scores by 12 points, a first-order effect.",
        )
        cat = self._category_id(client)
        before = client.get("/api/candidates?status=all").json()
        on_email = [c for c in before if c["email_id"] == corpus[0]]
        assert len(on_email) == 1
        original_id = on_email[0]["id"]

        body = client.post(
            f"/api/searches/{search_id}/hits/{hid}/keep",
            json={
                "tag": "STRONG CANDIDATE",
                "category_id": cat,
                "notes": "Search found this too.",
                "important": True,
            },
        ).json()
        assert body["candidate"]["id"] == original_id
        assert body["candidate"]["tag"] == "STRONG CANDIDATE"
        assert body["candidate"]["important"] is True
        assert body["candidate"]["topic"] == "Existing extraction"
        after = [c for c in client.get("/api/candidates?status=all").json() if c["email_id"] == corpus[0]]
        assert len(after) == 1

    def test_rejects_a_bad_tag_or_unmarked_keep(self, client, corpus):
        search_id = start_search()
        hid = _add_hit(search_id, corpus[0])
        cat = self._category_id(client)
        bad = client.post(
            f"/api/searches/{search_id}/hits/{hid}/keep",
            json={"tag": "WHATEVER", "category_id": cat, "important": True},
        )
        assert bad.status_code == 400
        unmarked = client.post(
            f"/api/searches/{search_id}/hits/{hid}/keep",
            json={
                "tag": "STRONG CANDIDATE",
                "category_id": cat,
                "important": False,
                "shortlisted": False,
            },
        )
        assert unmarked.status_code == 400

    def test_unknown_hit_is_a_404(self, client, corpus):
        search_id = start_search()
        resp = client.post(
            f"/api/searches/{search_id}/hits/9999/keep",
            json={"tag": "STRONG CANDIDATE", "important": True},
        )
        assert resp.status_code == 404

    def test_deleting_the_search_keeps_the_candidate(self, client, corpus):
        search_id = start_search()
        hid = _add_hit(search_id, corpus[0])
        cat = self._category_id(client)
        cid = client.post(
            f"/api/searches/{search_id}/hits/{hid}/keep",
            json={"tag": "STRONG CANDIDATE", "category_id": cat, "important": True},
        ).json()["candidate"]["id"]
        assert client.delete(f"/api/searches/{search_id}").status_code == 200
        listed = client.get("/api/candidates?status=all").json()
        assert any(c["id"] == cid for c in listed)
