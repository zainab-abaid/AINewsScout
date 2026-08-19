from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.publish import publish_snapshot

router = APIRouter()

_lock = threading.Lock()
_state: dict = {"status": "idle", "url": "", "error": ""}


class PublishStatus(BaseModel):
    status: str  # idle | running | done | error
    url: str = ""
    error: str = ""


@router.get("/publish", response_model=PublishStatus)
def get_publish_status():
    return PublishStatus(**_state)


@router.post("/publish", response_model=PublishStatus)
def start_publish():
    if not _lock.acquire(blocking=False):
        return PublishStatus(**_state)
    _state.update({"status": "running", "url": "", "error": ""})

    def _run():
        try:
            url = publish_snapshot()
            _state.update({"status": "done", "url": url, "error": ""})
        except Exception as exc:
            _state.update({"status": "error", "url": "", "error": str(exc)})
        finally:
            _lock.release()

    threading.Thread(target=_run, daemon=True).start()
    return PublishStatus(**_state)
