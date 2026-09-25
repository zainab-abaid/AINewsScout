from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "probe_scout.sqlite"
SKILLS_DIR = ROOT / "skills"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4"
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "high").strip() or "high"

# Idea search reads the emails in batches of four. An issue of this newsletter
# runs 55k-110k characters, so four of them land near 80k tokens: a large but
# comfortable fraction of the model's context, leaving plenty of room for high
# effort reasoning. The character budget only binds on unusually long issues,
# where it splits the batch rather than risking a truncated read.
IDEA_SEARCH_EMAILS_PER_CHUNK = max(
    1, int(os.getenv("IDEA_SEARCH_EMAILS_PER_CHUNK", "4"))
)
IDEA_SEARCH_CHUNK_CHARS = max(
    20_000, int(os.getenv("IDEA_SEARCH_CHUNK_CHARS", "320000"))
)

# Dedicated inbox pull (IMAP + app password).
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com").strip() or "imap.gmail.com"
IMAP_PORT = int(os.getenv("IMAP_PORT", "993") or "993")
IMAP_USER = os.getenv("IMAP_USER", "").strip()
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "").replace(" ", "").strip()
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX").strip() or "INBOX"
# Comma-separated From addresses to accept (case-insensitive substring match).
IMAP_ALLOWED_FROM = [
    part.strip().lower()
    for part in os.getenv("IMAP_ALLOWED_FROM", "zainab.abaid@emumba.com").split(",")
    if part.strip()
]
IMAP_SYNC_ENABLED = os.getenv("IMAP_SYNC_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
# Local hour (0-23) when the daily IMAP pull runs while the API is up.
IMAP_SYNC_HOUR = max(0, min(23, int(os.getenv("IMAP_SYNC_HOUR", "6") or "6")))

API_HOST = "127.0.0.1"
API_PORT = int(os.getenv("PORT", "8000"))


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
