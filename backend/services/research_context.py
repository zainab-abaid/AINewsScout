"""Admin-editable research context used by the extractor.

The on-disk skill file `01_genie_research_context.md` is the default. Once an
admin saves overrides, those live in SQLite (AppSetting) so deploys do not wipe
them and the committed skill file stays a safe fallback.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.config import SKILLS_DIR
from backend.database import session_scope
from backend.db import AppSetting

SETTING_KEY = "research_context_json"


def _default_from_skill() -> dict[str, Any]:
    """Best-effort parse of the skill file into editable sections."""
    path = SKILLS_DIR / "01_genie_research_context.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""

    priority_areas: list[dict[str, str]] = []
    past_probes: list[dict[str, str]] = []
    not_useful: list[str] = []

    # Priority areas: ### headings under "# Current higher-priority research areas"
    pri = re.search(
        r"# Current higher-priority research areas\s*(.*?)(?=\n# |\Z)",
        text,
        flags=re.S,
    )
    if pri:
        for m in re.finditer(r"## (.+?)\n+(.*?)(?=\n## |\Z)", pri.group(1), flags=re.S):
            priority_areas.append(
                {"name": m.group(1).strip(), "description": m.group(2).strip()}
            )

    # Past probes: ## N. Title under previous probes section
    past = re.search(
        r"# Previous Genie probes and hands-on investigations\s*(.*?)(?=\n# |\Z)",
        text,
        flags=re.S,
    )
    if past:
        for m in re.finditer(r"## (.+?)\n+(.*?)(?=\n## |\Z)", past.group(1), flags=re.S):
            past_probes.append(
                {"name": m.group(1).strip(), "description": m.group(2).strip()}
            )

    # Not useful bullets
    bad = re.search(r"# What is generally not useful\s*(.*?)(?=\n# |\Z)", text, flags=re.S)
    if bad:
        for line in bad.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                not_useful.append(line[2:].strip().rstrip(";."))

    return {
        "priority_areas": priority_areas,
        "past_probes": past_probes,
        "not_useful": not_useful,
        "source": "skill_file",
    }


def load_research_context() -> dict[str, Any]:
    with session_scope() as session:
        row = session.get(AppSetting, SETTING_KEY)
        if row and row.value.strip():
            try:
                data = json.loads(row.value)
                if isinstance(data, dict):
                    data["source"] = "database"
                    return data
            except json.JSONDecodeError:
                pass
    data = _default_from_skill()
    return data


def save_research_context(data: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "priority_areas": [
            {
                "name": str(item.get("name") or "").strip(),
                "description": str(item.get("description") or "").strip(),
            }
            for item in (data.get("priority_areas") or [])
            if str(item.get("name") or "").strip()
        ],
        "past_probes": [
            {
                "name": str(item.get("name") or "").strip(),
                "description": str(item.get("description") or "").strip(),
            }
            for item in (data.get("past_probes") or [])
            if str(item.get("name") or "").strip()
        ],
        "not_useful": [
            str(item).strip()
            for item in (data.get("not_useful") or [])
            if str(item).strip()
        ],
    }
    with session_scope() as session:
        row = session.get(AppSetting, SETTING_KEY)
        raw = json.dumps(payload, ensure_ascii=False)
        if row is None:
            session.add(AppSetting(key=SETTING_KEY, value=raw))
        else:
            row.value = raw
    payload["source"] = "database"
    return payload


def research_context_markdown(data: dict[str, Any] | None = None) -> str:
    """Compose the block injected into the extractor prompt."""
    ctx = data or load_research_context()
    lines = [
        "# Genie Research Context for Probe Scouting",
        "",
        "## Purpose",
        "",
        "Use this as background when screening AI newsletter emails for possible Genie probes.",
        "Priority areas are not a whitelist — a strong hands-on GenAI engineering topic outside them may still be selected.",
        "",
        "# Previous Genie probes and hands-on investigations",
        "",
    ]
    for i, probe in enumerate(ctx.get("past_probes") or [], start=1):
        lines.append(f"## {i}. {probe.get('name') or 'Untitled'}")
        lines.append("")
        if probe.get("description"):
            lines.append(probe["description"])
            lines.append("")
    lines.extend(["# Current higher-priority research areas", ""])
    lines.append(
        "A candidate that clearly belongs to one of these areas should be tagged "
        "**High Priority Research Area** when it also has a plausible hands-on investigation path."
    )
    lines.append("")
    for area in ctx.get("priority_areas") or []:
        lines.append(f"## {area.get('name') or 'Untitled'}")
        lines.append("")
        if area.get("description"):
            lines.append(area["description"])
            lines.append("")
    lines.extend(["# What is generally not useful", "", "Do not select material merely because it concerns:", ""])
    for item in ctx.get("not_useful") or []:
        lines.append(f"- {item};")
    lines.append("")
    lines.append(
        "A newsletter item can still contain a relevant technical candidate inside an otherwise "
        "irrelevant section. Extract the technical item and ignore the rest."
    )
    return "\n".join(lines)
