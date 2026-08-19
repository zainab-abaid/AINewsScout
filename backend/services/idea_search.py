"""Searching the stored emails for passages that answer a question.

The corpus is far larger than one model call can hold, so emails are packed into
batches and each batch is searched on its own. Findings from every batch are
concatenated by the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from openai import OpenAI

from backend.config import (
    IDEA_SEARCH_CHUNK_CHARS,
    IDEA_SEARCH_EMAILS_PER_CHUNK,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_REASONING_EFFORT,
)
from backend.prompts import idea_search_instructions
from backend.schemas import SearchFinding, SearchFindings
from backend.services.links import hydrate_excerpt_links

MARKER = "===== EMAIL id={id} | date={date} | subject={subject} ====="


@dataclass(frozen=True)
class SearchEmail:
    """The parts of a stored email a search needs."""

    id: int
    subject: str
    date: str
    body_md: str


def chunk_emails(
    emails: list[SearchEmail],
    per_chunk: Optional[int] = None,
    char_budget: Optional[int] = None,
) -> list[list[SearchEmail]]:
    """Group emails into batches small enough for one model call.

    A batch is closed when it reaches the email count or would exceed the
    character budget. An email larger than the whole budget is sent on its own
    rather than being split or dropped, so nothing is silently skipped.
    """
    limit = per_chunk or IDEA_SEARCH_EMAILS_PER_CHUNK
    budget = char_budget or IDEA_SEARCH_CHUNK_CHARS
    chunks: list[list[SearchEmail]] = []
    current: list[SearchEmail] = []
    used = 0
    for email in emails:
        size = len(email.body_md)
        too_many = len(current) >= limit
        too_big = current and used + size > budget
        if too_many or too_big:
            chunks.append(current)
            current = []
            used = 0
        current.append(email)
        used += size
    if current:
        chunks.append(current)
    return chunks


def build_chunk_input(question: str, chunk: list[SearchEmail]) -> str:
    parts = [
        "USER QUESTION:",
        question.strip(),
        "",
        f"EMAIL BATCH ({len(chunk)} email(s)):",
        "",
    ]
    for email in chunk:
        parts.append(
            MARKER.format(id=email.id, date=email.date or "(unknown)", subject=email.subject)
        )
        parts.append("")
        parts.append(email.body_md.strip())
        parts.append("")
    return "\n".join(parts)


def clean_findings(
    findings: list[SearchFinding], chunk: list[SearchEmail]
) -> list[SearchFinding]:
    """Keep findings that point at an email in this batch and carry a quote.

    A wrong id would link the reader to an unrelated newsletter, and an empty
    excerpt gives them nothing to read, so both are dropped rather than shown.
    """
    bodies = {e.id: e.body_md for e in chunk}
    kept: list[SearchFinding] = []
    for finding in findings:
        if finding.email_id not in bodies:
            continue
        excerpt = (finding.excerpt or "").strip()
        if not excerpt:
            continue
        kept.append(
            finding.model_copy(
                update={
                    "excerpt": hydrate_excerpt_links(excerpt, bodies[finding.email_id]),
                    "title": (finding.title or "").strip(),
                    "why_relevant": (finding.why_relevant or "").strip(),
                }
            )
        )
    return kept


def readable_model_error(exc: Exception) -> str:
    """The sentence the API sent, rather than a dump of the whole error body.

    An OpenAI error stringifies as `Error code: 429 - {'error': {'message': ...}}`,
    which buries the one line the reader needs (out of credits, rate limited, and
    so on) inside a Python dict repr.
    """
    body: Any = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        message = inner.get("message") if isinstance(inner, dict) else body.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    text = str(exc)
    found = re.search(r"'message': ['\"](.+?)['\"](?:, |\})", text)
    return found.group(1) if found else text


def search_chunk(question: str, chunk: list[SearchEmail]) -> list[SearchFinding]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=900.0)
    response = client.responses.parse(
        model=OPENAI_MODEL,
        instructions=idea_search_instructions(),
        input=build_chunk_input(question, chunk),
        text_format=SearchFindings,
        reasoning={"effort": OPENAI_REASONING_EFFORT},
        store=False,
    )
    parsed = response.output_parsed
    if parsed is None:
        raw = getattr(response, "output_text", "") or ""
        raise RuntimeError(f"Model returned no parsed JSON. Raw: {raw[:500]}")
    return clean_findings(parsed.findings, chunk)


def normalize_excerpt(text: str) -> str:
    """Strip links and punctuation so two quotes of the same passage compare equal."""
    stripped = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r" \1 ", text or "")
    stripped = re.sub(r"https?://\S+", " ", stripped)
    stripped = re.sub(r"[^0-9A-Za-z\u00C0-\u024F]+", " ", stripped)
    return stripped.strip().lower()


def excerpts_match(left: str, right: str) -> bool:
    """True when two quotes are the same passage, even if one is a shorter cut."""
    a = normalize_excerpt(left)
    b = normalize_excerpt(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    probe = shorter[:80]
    return len(probe) >= 24 and probe in longer
