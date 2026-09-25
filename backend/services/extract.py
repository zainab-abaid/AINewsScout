from __future__ import annotations

import json
from typing import Sequence

from openai import OpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_REASONING_EFFORT
from backend.prompts import extractor_instructions
from backend.schemas import ExtractionResult
from backend.services.links import hydrate_excerpt_links
from backend.services.llm_logs import record_llm_call


def openai_api_key() -> str:
    return OPENAI_API_KEY


def extract_candidates(
    subject: str,
    date_raw: str,
    body_md: str,
    categories: Sequence[str] = (),
    email_id: int | None = None,
) -> ExtractionResult:
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")

    instructions = extractor_instructions(categories)
    user = (
        f"Email title: {subject}\n"
        f"Email date: {date_raw}\n\n"
        f"{body_md}"
    )
    client = OpenAI(api_key=key, timeout=600.0)
    response = client.responses.parse(
        model=OPENAI_MODEL,
        instructions=instructions,
        input=user,
        text_format=ExtractionResult,
        reasoning={"effort": OPENAI_REASONING_EFFORT},
        store=False,
    )
    parsed = response.output_parsed
    if parsed is None:
        raw = getattr(response, "output_text", "") or ""
        record_llm_call(
            kind="extract",
            instructions_text=instructions,
            input_text=user,
            output_text=raw,
            model=OPENAI_MODEL,
            email_id=email_id,
            meta={"error": "no_parsed_json"},
        )
        raise RuntimeError(f"Model returned no parsed JSON. Raw: {raw[:500]}")
    for cand in parsed.candidates:
        cand.excerpt = hydrate_excerpt_links(cand.excerpt, body_md)
    record_llm_call(
        kind="extract",
        instructions_text=instructions,
        input_text=user,
        output_text=json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False, indent=2),
        model=OPENAI_MODEL,
        email_id=email_id,
        meta={"candidate_count": len(parsed.candidates)},
    )
    return parsed


def dump_raw(result: ExtractionResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
