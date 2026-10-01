# AINews Scout

Web app that pulls **AI News newsletters from a dedicated inbox**, extracts **Genie probe candidates** with OpenAI, and lets people review, categorise, mark, and search them.

The shared production app is [https://ainewsscout-production.up.railway.app](https://ainewsscout-production.up.railway.app). You can also run the same code locally. Emails, marks, and research context live in one SQLite file. That file is not in Git.

New to the codebase? Read [onboarding_docs/feature_development_guide_for_onboarding_developers.md](onboarding_docs/feature_development_guide_for_onboarding_developers.md) before changing features. Deploy details are in [docs/RAILWAY.md](docs/RAILWAY.md).

## What is stored where

| Data | Location |
| --- | --- |
| Emails, probe candidates, marks, categories, searches, jobs | `data/probe_scout.sqlite` locally. On Railway, the same filename on a volume mounted at `/app/data`. Gitignored. |
| Research context (probes, artifacts, priorities, not-useful) and LLM call logs | Tables in that same database. Empty databases are seeded once from `backend/seed/research_context_seed.json`. |
| OpenAI key, IMAP credentials, role tokens | `.env` locally. Railway Variables in production. Never commit them. |

Sync only adds new messages. Stored newsletters are not deleted.

Admin edits to research context or categories apply to **new extractions only**. They do not re-analyse mail already in the database and they do not wipe marks or comments. Deprecated categories stay on old candidates.

## Roles

| Role | Token | Can do |
| --- | --- | --- |
| Locked | none / wrong token | Access gate only |
| Viewer | `VIEWER_TOKEN` | Browse candidates, marked items, and AI search |
| Analyst | `ANALYST_TOKEN` | Mark, comment, categorise with existing categories, sync, extract, keep search hits |
| Admin | `ADMIN_TOKEN` | Everything an analyst can do, plus the Admin tab |

When `VIEWER_TOKEN` is set, the UI stays locked until a valid token is entered. Analyst and admin tokens unlock the app as well. Use **Switch role** in the header to change. For a local-only checkout you may leave `VIEWER_TOKEN` empty, which makes anonymous requests a viewer. Production must set it.

Generate a token with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node 20+
- An OpenAI API key
- The dedicated Gmail inbox (`IMAP_USER`) with IMAP and an app password
- Forwards of AINews into that inbox. The allow-list address is `IMAP_ALLOWED_FROM`

## Setup

```bash
git clone https://github.com/zainab-abaid/AINewsScout.git
cd AINewsScout

cp .env.example .env
# Fill in OPENAI_API_KEY, IMAP_USER, IMAP_PASSWORD, IMAP_ALLOWED_FROM, and the three tokens

./run_dev.sh
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The API listens on port 8000. Vite proxies `/api` to it.

How the inbox is filtered, and how the live Railway service is configured, is in [onboarding_docs/inbox_auth_and_railway.md](onboarding_docs/inbox_auth_and_railway.md).

### Inbox env vars

| Variable | Purpose |
| --- | --- |
| `IMAP_HOST` | Default `imap.gmail.com` |
| `IMAP_PORT` | Default `993` |
| `IMAP_USER` | Dedicated inbox address |
| `IMAP_PASSWORD` | App password, not the normal Gmail password |
| `IMAP_FOLDER` | Default `INBOX` |
| `IMAP_ALLOWED_FROM` | Comma-separated addresses. A message matches if one appears in From, To, Cc, or the forward headers. Gmail auto-forward keeps the newsletter’s original From. |
| `IMAP_SYNC_ENABLED` | `1` to enable the pull (default) |
| `IMAP_SYNC_HOUR` | Hour `0–23` on the API process clock. Railway is UTC. `6` is 06:00 UTC (16:00 AEST). |
| `VIEWER_TOKEN` | Required to open a hosted app |
| `ANALYST_TOKEN` | Marks, sync, extract |
| `ADMIN_TOKEN` | Research context and categories |

Optional IMAP check:

```bash
uv run python -m backend.tools.test_imap_pull          # dry run
uv run python -m backend.tools.test_imap_pull --store  # write new matches
```

While the API is running it pulls once on startup and again every day at `IMAP_SYNC_HOUR`. **Sync inbox now** pulls immediately and then extracts new or pending emails. AI search does not pull the inbox.

## Application

Signed-in admins see four tabs. Viewers and analysts see the first three.

### Important items extracted from emails

Filters for model ranking and marks, category toggles, and unprocessed items. Analysts mark Important or Shortlist. The first time either is turned on, an in-app comment box opens. Excerpts keep newsletter links. The email title opens the full Markdown body.

### Review marked items

Important and shortlisted items, with comments and categories. The filter bar stays put while you scroll.

### AI search

Ask a question across newsletters **already in the database**. The default range is the last two weeks, clamped to stored issues. Dates in the future or outside the stored span are rejected. Findings can be added to marked items. Past searches can be reopened. Deleting a running search cancels it.

This search does not contact Gmail. New mail shows up here only after a sync has stored it.

### Admin

Priorities, past probes, related artifacts, the not-useful list, categories, a live prompt preview, and LLM call logs.

A new probe is added from pasted text, a URL, or a PDF — one of those, then Submit. An LLM writes the title and short description. Each probe has an editable date. Probes are listed newest date first. Older probes with no date stay at the bottom until someone fills the date in.

## Tests

```bash
uv run pytest
cd frontend && npm test && ./node_modules/.bin/tsc -b
```

## Layout

```
backend/           FastAPI app, IMAP sync, extraction, search, SQLite models
backend/tools/     IMAP pull smoke test
frontend/          Vite + React UI
skills/            Extractor and AI-search prompts
tests/             Backend tests (temporary database)
onboarding_docs/   Guide for someone changing the app
docs/RAILWAY.md    Host setup
data/              Local SQLite file, created at runtime, gitignored
```

## Hosting

Production deploys from `main`. The database stays on the Railway volume across deploys. See [docs/RAILWAY.md](docs/RAILWAY.md).
