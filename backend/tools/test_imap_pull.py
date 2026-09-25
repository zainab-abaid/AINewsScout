"""Pull allowed messages from the dedicated IMAP inbox.

By default only prints what would be ingested; pass --store to write new
emails into the local database.

    uv run python -m backend.tools.test_imap_pull
    uv run python -m backend.tools.test_imap_pull --store
"""

from __future__ import annotations

import argparse
import json

from backend.config import IMAP_ALLOWED_FROM, IMAP_FOLDER, IMAP_HOST, IMAP_USER
from backend.database import init_db
from backend.services.imap_sync import fetch_and_store, imap_configured, imap_status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        action="store_true",
        help="write new matching emails into the database (default: dry run)",
    )
    args = parser.parse_args()

    print(json.dumps(imap_status(), indent=2))
    if not imap_configured():
        print("IMAP is not configured. Fill IMAP_USER / IMAP_PASSWORD / IMAP_ALLOWED_FROM in .env")
        return 1

    print(
        f"\nPulling from {IMAP_USER} @ {IMAP_HOST}/{IMAP_FOLDER}\n"
        f"Allowed From: {', '.join(IMAP_ALLOWED_FROM)}\n"
        f"Mode: {'STORE' if args.store else 'DRY RUN'}\n"
    )
    init_db()

    def on_progress(p: dict) -> None:
        phase = p.get("phase")
        if phase == "fetching" and p.get("dry_run_subject"):
            print(f"  would store: {p['dry_run_subject']}")
        elif phase in {"connecting", "fetched"}:
            print(f"[{phase}] listed={p.get('listed')} matched={p.get('matched')} "
                  f"new={p.get('new_emails')} skipped={p.get('skipped')} "
                  f"rejected_from={p.get('rejected_from')}")

    counts, new_ids = fetch_and_store(progress=on_progress, dry_run=not args.store)
    print("\nResult:", counts)
    if new_ids:
        print("Stored email ids:", new_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
