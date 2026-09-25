"""Optional LLM assist: turn a PDF or web page into a short probe/artifact blurb.

Test feature — text only (no images/video). Admin can always enter title and
description manually instead.
"""

from __future__ import annotations

import io
import re
from typing import Literal

import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
from pypdf import PdfReader
from pydantic import BaseModel, Field

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.services.llm_logs import record_llm_call

MAX_CHARS = 40_000

INGEST_INSTRUCTIONS = """You summarise Genie R&D material for a probe-scouting assistant.

Given the source text, produce:
- title: a short clear name (no numbering prefix)
- description: 2–3 sentences describing what was investigated or built, what was compared or measured, and why it matters for GenAI application / agent engineering.

Do not invent claims not supported by the source. If the source is thin, say so briefly in the description.
"""


class IngestSummary(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


Kind = Literal["probe", "artifact"]


def openai_api_key() -> str:
    return OPENAI_API_KEY


def extract_text_from_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n\n".join(p.strip() for p in parts if p and p.strip())
    if not text.strip():
        raise ValueError("Could not extract text from that PDF (scanned images are not supported).")
    return text[:MAX_CHARS]


def extract_text_from_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    with httpx.Client(follow_redirects=True, timeout=45.0) as client:
        res = client.get(
            raw,
            headers={"User-Agent": "AINewsScout/1.0 (research-context ingest)"},
        )
        res.raise_for_status()
        ctype = (res.headers.get("content-type") or "").lower()
        if "html" not in ctype and "text" not in ctype and "json" not in ctype:
            raise ValueError(
                f"Unsupported content type ({ctype or 'unknown'}). "
                "Only HTML/text pages are supported — not images or video."
            )
        body = res.text
    soup = BeautifulSoup(body, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 80:
        raise ValueError("Page had almost no extractable text.")
    return text[:MAX_CHARS]


def summarise_source(
    *,
    kind: Kind,
    source_text: str,
    source_label: str,
) -> IngestSummary:
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing from .env")
    label = "past Genie probe" if kind == "probe" else "related Genie artifact"
    user = (
        f"Summarise this source as a {label}.\n"
        f"Source label: {source_label}\n\n"
        f"----- SOURCE TEXT -----\n{source_text}"
    )
    client = OpenAI(api_key=key, timeout=180.0)
    response = client.responses.parse(
        model=OPENAI_MODEL,
        instructions=INGEST_INSTRUCTIONS,
        input=user,
        text_format=IngestSummary,
        store=False,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("Model returned no structured summary")
    record_llm_call(
        kind=f"{kind}_ingest",
        instructions_text=INGEST_INSTRUCTIONS,
        input_text=user,
        output_text=parsed.model_dump_json(indent=2),
        model=OPENAI_MODEL,
        meta={"source_label": source_label},
    )
    return parsed
