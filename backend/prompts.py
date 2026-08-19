from __future__ import annotations

from typing import Sequence

from backend.config import SKILLS_DIR


def _read_skill(name: str) -> str:
    path = SKILLS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Missing skill file: {path}")
    return path.read_text(encoding="utf-8")


def idea_search_instructions() -> str:
    rules = _read_skill("03_idea_search_over_emails.md")
    return (
        "Follow the evidence search skill below. Search only the emails given "
        "in this batch and return structured JSON matching the schema.\n\n"
        "===== EVIDENCE SEARCH SKILL =====\n\n"
        f"{rules}\n"
    )


def extractor_instructions(categories: Sequence[str] = ()) -> str:
    rules = _read_skill("02_single_email_candidate_extractor.md")
    context = _read_skill("01_genie_research_context.md")
    cat_block = ""
    if categories:
        listed = "\n".join(f"- {c}" for c in categories)
        cat_block = (
            "\n\n===== AVAILABLE CATEGORIES =====\n\n"
            "For every candidate, set `category` to the single best-fit name from this list, "
            "or `null` if none fits well. Use the exact string from the list.\n\n"
            f"{listed}"
        )
    return (
        "Follow the extractor skill and the research context below. "
        "Screen this one email only. Return structured JSON matching the schema.\n\n"
        "===== EXTRACTOR SKILL =====\n\n"
        f"{rules}\n\n"
        "===== GENIE RESEARCH CONTEXT =====\n\n"
        f"{context}"
        f"{cat_block}\n"
    )
