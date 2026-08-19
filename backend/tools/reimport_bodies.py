"""Re-download stored emails and rebuild their Markdown.

Sync skips messages already in the database, so an email keeps whichever body
the converter produced at the time it arrived. Run this after the converter
improves, to bring older emails up to the current formatting. Marks, comments
and extracted candidates are not touched.

    uv run python -m backend.tools.reimport_bodies --dry-run
    uv run python -m backend.tools.reimport_bodies
"""

from __future__ import annotations

import argparse

from backend.database import init_db
from backend.services.gmail_sync import reimport_bodies


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing to the database",
    )
    args = parser.parse_args()

    init_db()
    try:
        counts = reimport_bodies(dry_run=args.dry_run, report=print)
    except RuntimeError as exc:
        print(f"Cannot re-import: {exc}")
        return 1

    print(
        "\nchecked {checked}, {verb} {updated}, unchanged {unchanged}, failed {failed}".format(
            verb="would update" if args.dry_run else "updated", **counts
        )
    )
    if args.dry_run and counts["updated"]:
        print("Re-run without --dry-run to apply.")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
