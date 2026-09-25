"""Background daily IMAP pull while the API process is running."""

from __future__ import annotations

import logging
import threading
import time

from backend.config import IMAP_SYNC_ENABLED, IMAP_SYNC_HOUR
from backend.services.imap_sync import (
    imap_configured,
    run_imap_sync_once,
    seconds_until_sync_hour,
)

log = logging.getLogger(__name__)


def start_imap_daily_sync() -> None:
    """Pull once on startup, then once per day at IMAP_SYNC_HOUR (local time).

    The startup pull catches mail that arrived while the API was down. The
    daily timer covers the steady state while the process stays up.
    """
    if not (IMAP_SYNC_ENABLED and imap_configured()):
        log.info("IMAP daily sync not started (disabled or not configured)")
        return

    def loop() -> None:
        log.info(
            "IMAP sync started (startup pull + daily at local hour=%s)",
            IMAP_SYNC_HOUR,
        )
        try:
            run_imap_sync_once()
        except Exception:
            log.exception("IMAP startup sync failed")
        while True:
            wait = seconds_until_sync_hour()
            log.info("IMAP daily sync sleeping %.0f seconds", wait)
            time.sleep(wait)
            try:
                run_imap_sync_once()
            except Exception:
                log.exception("IMAP daily sync failed")

    threading.Thread(target=loop, name="imap-daily-sync", daemon=True).start()
