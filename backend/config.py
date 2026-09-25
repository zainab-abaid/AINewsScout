from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

# Local default: <repo>/data. On Railway mount a volume at /app/data and set DATA_DIR=/app/data.
_data_env = os.getenv("DATA_DIR", "").strip()
DATA_DIR = Path(_data_env) if _data_env else (ROOT / "data")
DB_PATH = DATA_DIR / "probe_scout.sqlite"
SKILLS_DIR = ROOT / "skills"
FRONTEND_DIST = ROOT / "frontend" / "dist"

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

API_HOST = os.getenv("API_HOST", "0.0.0.0" if os.getenv("PORT") else "127.0.0.1").strip() or "127.0.0.1"
API_PORT = int(os.getenv("PORT", "8000"))

# Comma-separated browser origins allowed to call the API (local Vite defaults).
# When the UI is served from the same FastAPI process, same-origin needs no CORS.
CORS_ORIGINS = [
    part.strip()
    for part in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if part.strip()
]

# Access tokens for hosted / shared use. Empty = that role cannot unlock.
# If VIEWER_TOKEN is set, the app stays locked until a valid token is provided.
# If VIEWER_TOKEN is empty (local convenience), reads are open as viewer.
VIEWER_TOKEN = os.getenv("VIEWER_TOKEN", "").strip()
ANALYST_TOKEN = os.getenv("ANALYST_TOKEN", "").strip()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
