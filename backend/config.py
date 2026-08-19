from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)
# Local HTTP loopback is required for the Gmail OAuth redirect.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "probe_scout.sqlite"
SKILLS_DIR = ROOT / "skills"
GMAIL_CLIENT_PATH = DATA_DIR / "gmail_oauth_client.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4"
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "high").strip() or "high"
GMAIL_LABEL = os.getenv("GMAIL_LABEL", "AINews").strip() or "AINews"

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
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "").strip()
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "").strip()

API_HOST = "127.0.0.1"
API_PORT = int(os.getenv("PORT", "8000"))

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
KEYRING_SERVICE = "probe-scout"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def gmail_redirect_uri() -> str:
    return f"http://{API_HOST}:{API_PORT}/api/gmail/callback"
