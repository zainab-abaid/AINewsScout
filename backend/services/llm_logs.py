"""Persist LLM call payloads for admin review."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlmodel import select

from backend.database import session_scope
from backend.db import LlmCallLog


def record_llm_call(
    *,
    kind: str,
    instructions_text: str,
    input_text: str,
    output_text: str,
    model: str = "",
    email_id: Optional[int] = None,
    meta: Optional[dict[str, Any]] = None,
) -> int:
    with session_scope() as session:
        row = LlmCallLog(
            kind=kind,
            email_id=email_id,
            model=model or "",
            instructions_text=instructions_text or "",
            input_text=input_text or "",
            output_text=output_text or "",
            meta_json=json.dumps(meta or {}, ensure_ascii=False),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return int(row.id or 0)


def list_llm_logs(*, kind: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    with session_scope() as session:
        stmt = select(LlmCallLog).order_by(LlmCallLog.id.desc()).limit(limit)
        if kind:
            stmt = select(LlmCallLog).where(LlmCallLog.kind == kind).order_by(
                LlmCallLog.id.desc()
            ).limit(limit)
        rows = session.exec(stmt).all()
        return [_summary(r) for r in rows]


def get_llm_log(log_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(LlmCallLog, log_id)
        if not row:
            return None
        return _detail(row)


def _summary(row: LlmCallLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "email_id": row.email_id,
        "model": row.model,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "input_preview": (row.input_text or "")[:160].replace("\n", " "),
        "output_preview": (row.output_text or "")[:160].replace("\n", " "),
    }


def _detail(row: LlmCallLog) -> dict[str, Any]:
    try:
        meta = json.loads(row.meta_json or "{}")
    except json.JSONDecodeError:
        meta = {}
    return {
        **_summary(row),
        "instructions_text": row.instructions_text,
        "input_text": row.input_text,
        "output_text": row.output_text,
        "meta": meta,
    }
