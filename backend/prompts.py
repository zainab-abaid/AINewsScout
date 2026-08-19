from __future__ import annotations

from backend.config import SKILLS_DIR


def _read_skill(name: str) -> str:
    path = SKILLS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Missing skill file: {path}")
    return path.read_text(encoding="utf-8")


def extractor_instructions() -> str:
    rules = _read_skill("02_single_email_candidate_extractor.md")
    context = _read_skill("01_genie_research_context.md")
    return (
        "Follow the extractor skill and the research context below. "
        "Screen this one email only. Return structured JSON matching the schema.\n\n"
        "===== EXTRACTOR SKILL =====\n\n"
        f"{rules}\n\n"
        "===== GENIE RESEARCH CONTEXT =====\n\n"
        f"{context}\n"
    )
