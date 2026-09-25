"""Admin-editable research context used by the extractor.

All sections live in SQLite tables. A committed seed JSON boots empty
databases; the old skills/01 markdown file is no longer used at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlmodel import func, select

from backend.database import session_scope
from backend.db import (
    AppSetting,
    ResearchArtifact,
    ResearchNotUseful,
    ResearchPriority,
    ResearchProbe,
)

SEED_PATH = Path(__file__).resolve().parent.parent / "seed" / "research_context_seed.json"
LEGACY_SETTING_KEY = "research_context_json"

PURPOSE_PREAMBLE = """# Genie Research Context for Probe Scouting

## Purpose

Use this as background when screening AI newsletter emails for possible Genie probes.

It tells you:

- what Genie has already investigated;
- what kinds of technical developments tend to catch our attention; and
- which areas are currently higher priority.

The priority areas are **not a whitelist**. A strong, hands-on GenAI engineering topic outside them may still be selected.
"""


def _max_order(session, model) -> int:
    return int(session.exec(select(func.max(model.sort_order))).one() or 0)


def seed_research_context_if_empty() -> None:
    """Populate tables from seed JSON (and migrate legacy AppSetting once)."""
    with session_scope() as session:
        has_any = (
            session.exec(select(ResearchProbe.id).limit(1)).first() is not None
            or session.exec(select(ResearchPriority.id).limit(1)).first() is not None
            or session.exec(select(ResearchArtifact.id).limit(1)).first() is not None
            or session.exec(select(ResearchNotUseful.id).limit(1)).first() is not None
        )
        if has_any:
            return

        data: dict[str, Any] = {}
        if SEED_PATH.is_file():
            data = json.loads(SEED_PATH.read_text(encoding="utf-8"))

        legacy = session.get(AppSetting, LEGACY_SETTING_KEY)
        if legacy and legacy.value.strip():
            try:
                parsed = json.loads(legacy.value)
                if isinstance(parsed, dict):
                    # Prefer previously saved admin edits when present.
                    if parsed.get("past_probes") or parsed.get("probes"):
                        data["probes"] = parsed.get("probes") or parsed.get("past_probes")
                    if parsed.get("artifacts"):
                        data["artifacts"] = parsed["artifacts"]
                    if parsed.get("priority_areas"):
                        data["priority_areas"] = parsed["priority_areas"]
                    if parsed.get("not_useful"):
                        data["not_useful"] = parsed["not_useful"]
            except json.JSONDecodeError:
                pass

        if not data and SEED_PATH.is_file():
            data = json.loads(SEED_PATH.read_text(encoding="utf-8"))

        for i, item in enumerate(data.get("probes") or data.get("past_probes") or []):
            title = str(item.get("name") or item.get("title") or "").strip()
            if not title:
                continue
            session.add(
                ResearchProbe(
                    title=title,
                    description=str(item.get("description") or "").strip(),
                    source_kind="manual",
                    sort_order=i,
                )
            )
        for i, item in enumerate(data.get("artifacts") or []):
            title = str(item.get("name") or item.get("title") or "").strip()
            if not title:
                continue
            session.add(
                ResearchArtifact(
                    title=title,
                    description=str(item.get("description") or "").strip(),
                    source_kind="manual",
                    sort_order=i,
                )
            )
        for i, item in enumerate(data.get("priority_areas") or []):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            session.add(
                ResearchPriority(
                    name=name,
                    description=str(item.get("description") or "").strip(),
                    sort_order=i,
                )
            )
        for i, text in enumerate(data.get("not_useful") or []):
            t = str(text).strip()
            if not t:
                continue
            session.add(ResearchNotUseful(text=t, sort_order=i))


def load_research_context() -> dict[str, Any]:
    with session_scope() as session:
        probes = session.exec(
            select(ResearchProbe).order_by(ResearchProbe.sort_order, ResearchProbe.id)
        ).all()
        artifacts = session.exec(
            select(ResearchArtifact).order_by(
                ResearchArtifact.sort_order, ResearchArtifact.id
            )
        ).all()
        priorities = session.exec(
            select(ResearchPriority).order_by(
                ResearchPriority.sort_order, ResearchPriority.id
            )
        ).all()
        not_useful = session.exec(
            select(ResearchNotUseful).order_by(
                ResearchNotUseful.sort_order, ResearchNotUseful.id
            )
        ).all()
        return {
            "probes": [
                {
                    "id": p.id,
                    "title": p.title,
                    "description": p.description,
                    "source_url": p.source_url,
                    "source_kind": p.source_kind,
                    "sort_order": p.sort_order,
                }
                for p in probes
            ],
            "artifacts": [
                {
                    "id": a.id,
                    "title": a.title,
                    "description": a.description,
                    "source_url": a.source_url,
                    "source_kind": a.source_kind,
                    "sort_order": a.sort_order,
                }
                for a in artifacts
            ],
            "priority_areas": [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "sort_order": r.sort_order,
                }
                for r in priorities
            ],
            "not_useful": [
                {"id": n.id, "text": n.text, "sort_order": n.sort_order}
                for n in not_useful
            ],
            "source": "database",
        }


def research_context_markdown(data: dict[str, Any] | None = None) -> str:
    """Compose the block injected into the extractor prompt."""
    ctx = data or load_research_context()
    lines = [PURPOSE_PREAMBLE.rstrip(), "", "# Previous Genie probes and hands-on investigations", ""]
    for i, probe in enumerate(ctx.get("probes") or [], start=1):
        title = probe.get("title") or probe.get("name") or "Untitled"
        lines.append(f"## {i}. {title}")
        lines.append("")
        if probe.get("description"):
            lines.append(str(probe["description"]))
            lines.append("")
    lines.extend(
        [
            "# Related Genie artifacts the scout should know about",
            "",
            "These were not necessarily published as numbered probes, but they represent "
            "existing Genie work and may affect novelty or suggest extensions.",
            "",
        ]
    )
    for art in ctx.get("artifacts") or []:
        title = art.get("title") or art.get("name") or "Untitled"
        lines.append(f"## {title}")
        lines.append("")
        if art.get("description"):
            lines.append(str(art["description"]))
            lines.append("")
    lines.extend(
        [
            "# Current higher-priority research areas",
            "",
            "A candidate that clearly belongs to one of these areas should be tagged "
            "**High Priority Research Area** when it also has a plausible hands-on investigation path.",
            "",
        ]
    )
    for area in ctx.get("priority_areas") or []:
        lines.append(f"## {area.get('name') or 'Untitled'}")
        lines.append("")
        if area.get("description"):
            lines.append(str(area["description"]))
            lines.append("")
    lines.extend(
        [
            "# What is generally not useful",
            "",
            "Do not select material merely because it concerns:",
            "",
        ]
    )
    for item in ctx.get("not_useful") or []:
        text = item.get("text") if isinstance(item, dict) else item
        if text:
            lines.append(f"- {text};")
    lines.append("")
    lines.append(
        "A newsletter item can still contain a relevant technical candidate inside an otherwise "
        "irrelevant section. Extract the technical item and ignore the rest."
    )
    return "\n".join(lines)


def add_probe(
    *,
    title: str,
    description: str = "",
    source_url: str | None = None,
    source_kind: str = "manual",
) -> dict[str, Any]:
    with session_scope() as session:
        order = _max_order(session, ResearchProbe) + 1
        row = ResearchProbe(
            title=title.strip(),
            description=description.strip(),
            source_url=source_url,
            source_kind=source_kind,
            sort_order=order,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return {
            "id": row.id,
            "title": row.title,
            "description": row.description,
            "source_url": row.source_url,
            "source_kind": row.source_kind,
            "sort_order": row.sort_order,
        }


def update_probe(probe_id: int, **fields: Any) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(ResearchProbe, probe_id)
        if not row:
            return None
        if "title" in fields and fields["title"] is not None:
            row.title = str(fields["title"]).strip()
        if "description" in fields and fields["description"] is not None:
            row.description = str(fields["description"]).strip()
        session.add(row)
        session.flush()
        session.refresh(row)
        return {
            "id": row.id,
            "title": row.title,
            "description": row.description,
            "source_url": row.source_url,
            "source_kind": row.source_kind,
            "sort_order": row.sort_order,
        }


def delete_probe(probe_id: int) -> bool:
    with session_scope() as session:
        row = session.get(ResearchProbe, probe_id)
        if not row:
            return False
        session.delete(row)
        return True


def add_artifact(
    *,
    title: str,
    description: str = "",
    source_url: str | None = None,
    source_kind: str = "manual",
) -> dict[str, Any]:
    with session_scope() as session:
        order = _max_order(session, ResearchArtifact) + 1
        row = ResearchArtifact(
            title=title.strip(),
            description=description.strip(),
            source_url=source_url,
            source_kind=source_kind,
            sort_order=order,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return {
            "id": row.id,
            "title": row.title,
            "description": row.description,
            "source_url": row.source_url,
            "source_kind": row.source_kind,
            "sort_order": row.sort_order,
        }


def update_artifact(artifact_id: int, **fields: Any) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(ResearchArtifact, artifact_id)
        if not row:
            return None
        if "title" in fields and fields["title"] is not None:
            row.title = str(fields["title"]).strip()
        if "description" in fields and fields["description"] is not None:
            row.description = str(fields["description"]).strip()
        session.add(row)
        session.flush()
        session.refresh(row)
        return {
            "id": row.id,
            "title": row.title,
            "description": row.description,
            "source_url": row.source_url,
            "source_kind": row.source_kind,
            "sort_order": row.sort_order,
        }


def delete_artifact(artifact_id: int) -> bool:
    with session_scope() as session:
        row = session.get(ResearchArtifact, artifact_id)
        if not row:
            return False
        session.delete(row)
        return True


def add_priority(*, name: str, description: str = "") -> dict[str, Any]:
    with session_scope() as session:
        order = _max_order(session, ResearchPriority) + 1
        row = ResearchPriority(
            name=name.strip(), description=description.strip(), sort_order=order
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "sort_order": row.sort_order,
        }


def update_priority(priority_id: int, **fields: Any) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(ResearchPriority, priority_id)
        if not row:
            return None
        if "name" in fields and fields["name"] is not None:
            row.name = str(fields["name"]).strip()
        if "description" in fields and fields["description"] is not None:
            row.description = str(fields["description"]).strip()
        session.add(row)
        session.flush()
        session.refresh(row)
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "sort_order": row.sort_order,
        }


def delete_priority(priority_id: int) -> bool:
    with session_scope() as session:
        row = session.get(ResearchPriority, priority_id)
        if not row:
            return False
        session.delete(row)
        return True


def add_not_useful(text: str) -> dict[str, Any]:
    with session_scope() as session:
        order = _max_order(session, ResearchNotUseful) + 1
        row = ResearchNotUseful(text=text.strip(), sort_order=order)
        session.add(row)
        session.flush()
        session.refresh(row)
        return {"id": row.id, "text": row.text, "sort_order": row.sort_order}


def update_not_useful(item_id: int, text: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(ResearchNotUseful, item_id)
        if not row:
            return None
        row.text = text.strip()
        session.add(row)
        session.flush()
        session.refresh(row)
        return {"id": row.id, "text": row.text, "sort_order": row.sort_order}


def delete_not_useful(item_id: int) -> bool:
    with session_scope() as session:
        row = session.get(ResearchNotUseful, item_id)
        if not row:
            return False
        session.delete(row)
        return True
