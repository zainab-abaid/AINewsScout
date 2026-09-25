# AINews Scout

Local web app that pulls **AI News newsletters from a dedicated inbox**, extracts **Genie probe candidates** with OpenAI, and lets you review, categorise, and mark them on your machine.

Each person clones the repo and runs it locally. Emails, probe ideas, and your marks live in a local SQLite database. Nothing is hosted and nothing is shared between users.

## What is stored where

| Data | Location |
| --- | --- |
| Emails, probe candidates, your marks, categories, job progress | `data/probe_scout.sqlite` (created on first run, gitignored) |
| Research context (probes, artifacts, priorities, not-useful) + LLM call logs | SQLite tables (seeded once from `backend/seed/research_context_seed.json`) |
| OpenAI key, IMAP inbox credentials, role tokens | `.env` (gitignored) |

Nothing in `data/` or `.env` is ever committed. Historic emails already in the database stay there permanently — sync only adds new messages.

### Research context (database)

Past probes, related artifacts, higher-priority research areas, and the not-useful list live in SQLite. The extractor prompt is composed from those rows on every run. Seed content ships in `backend/seed/research_context_seed.json` for empty databases. Extractor rules remain in `skills/02_…` and `skills/03_…`.

**Admin changes never re-analyse old newsletters** and never wipe marks or comments. New categories and deprecated categories apply to **new extractions only**; old candidates keep their existing category.

### Roles

| Role | Token | Can do |
| --- | --- | --- |
| Locked | none / wrong token | No content — access gate only |
| Viewer | `VIEWER_TOKEN` | Browse candidates, marked items, and semantic search |
| Analyst | `ANALYST_TOKEN` | Mark / comment / categorise (existing categories), sync, extract, keep search hits |
| Admin | `ADMIN_TOKEN` | Everything analyst can, plus Admin tab (research context + add/deprecate categories) |

When `VIEWER_TOKEN` is set, the UI stays locked until a valid token is entered. Analyst/admin tokens also unlock the app. Use **Switch role** in the header to change. For local-only convenience you may leave `VIEWER_TOKEN` empty (open viewer); set it before hosting.

### Env vs config, and hosting

Use **environment variables** (via `.env` locally, or the host’s secret store in production) — not a committed config file — for `OPENAI_API_KEY`, IMAP credentials, and role tokens. `.env` is gitignored so tokens are not pushed to GitHub.

On a host (Railway, Fly, Render, a VM, etc.):

- Set the same variables in the platform’s **secrets / environment** UI; do not bake them into the image or repo.
- Restrict who can read the host dashboard; rotate tokens if someone leaves.
- Prefer HTTPS and keep the API off the public internet if only a small team needs write access (or put it behind your org VPN / SSO later).
- A `.env` file on a server is only as safe as filesystem permissions and who can SSH in — platform secrets are usually better once you host.

Generate tokens with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put them in `.env` as `VIEWER_TOKEN`, `ANALYST_TOKEN`, and `ADMIN_TOKEN` (see `.env.example`).

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node 20+
- An OpenAI API key in `.env`
- A dedicated free inbox (for example a second Gmail) with IMAP enabled and an **app password**
- Your main mailbox forwarding AINews newsletters into that dedicated inbox

## Setup

### 1. Forward newsletters into the dedicated inbox

On your **main** Gmail (or wherever the newsletters arrive):

1. Create or keep a filter/label for AINews (for example From `swyx+ainews@substack.com` → label `AINews`).
2. Add the dedicated inbox address as a forwarding address and verify it.
3. Add a filter action: for that label (or sender), **Forward to** the dedicated inbox.

Manual forwards also work for testing: forward a newsletter so the dedicated inbox shows **From:** you (the address listed in `IMAP_ALLOWED_FROM`).

### 2. Create an app password on the dedicated inbox

For a dedicated Gmail:

1. Enable [2-Step Verification](https://myaccount.google.com/security).
2. Create an [App password](https://myaccount.google.com/apppasswords) named e.g. `AINewsScout`.
3. Put the address and app password in `.env` (see below).

### 3. Install and run

```bash
git clone https://github.com/zainab-abaid/AINewsScout.git
cd AINewsScout

cp .env.example .env
# Fill in OPENAI_API_KEY, IMAP_USER, IMAP_PASSWORD, IMAP_ALLOWED_FROM

./run_dev.sh
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The API listens on `127.0.0.1:8000` only.

### 4. Inbox env vars

| Variable | Purpose |
| --- | --- |
| `IMAP_HOST` | Default `imap.gmail.com` |
| `IMAP_PORT` | Default `993` |
| `IMAP_USER` | Dedicated inbox address |
| `IMAP_PASSWORD` | App password (not your normal login password) |
| `IMAP_FOLDER` | Default `INBOX` |
| `IMAP_ALLOWED_FROM` | Comma-separated From filters (only these messages are ingested) |
| `IMAP_SYNC_ENABLED` | `1` to enable auto pull (default) |
| `IMAP_SYNC_HOUR` | Local hour `0–23` for the daily pull while the API is running (default `6`) |
| `VIEWER_TOKEN` | Shared secret required to open the app (browse only) |
| `ANALYST_TOKEN` | Shared secret for analyst sign-in (marks, sync, extract) |
| `ADMIN_TOKEN` | Shared secret for admin sign-in (research context + taxonomy) |

Optional smoke test (does not need the UI):

```bash
uv run python -m backend.tools.test_imap_pull          # dry run
uv run python -m backend.tools.test_imap_pull --store  # write new matches to the DB
```

### Sync behaviour

- While the API is running, the app **pulls once on startup** and again **daily** at `IMAP_SYNC_HOUR`.
- **Sync inbox now** in the UI pulls immediately, then extracts probe ideas from new / pending emails.
- Only messages whose From matches `IMAP_ALLOWED_FROM` are stored. Everything already in the DB is left alone (including older issues synced under the previous mechanism).
- Emails are permanent. Nothing in the app deletes a stored newsletter.

## Application features

The UI has four tabs when signed in as admin: **Important items extracted from emails**, **Review marked items**, **Semantic search**, and **Admin**. Viewers and analysts see the first three.

### Important items extracted from emails

- Filters for model ranking and your marks; category toggles; **Show unprocessed items only**.
- Mark Important / Shortlist with optional comments; add categories on any card.
- Excerpts keep newsletter links; the email title opens the full Markdown body and scrolls to the passage.

### Review marked items

Everything you marked important or shortlisted, with editable comments and category changes.

### Search for ideas

Ask your own question across whole newsletters already in the database (historic and new):

> List all the studies and papers mentioned in the emails that conclude that harnesses affect how well models perform on tasks in different benchmarks.

- Searches the **local database** for the date range. Historic emails stay searchable forever.
- If the inbox is configured, the search job also does a quick inbox pull first so brand-new forwards are included, then reads every email in the range in batches.
- Findings can be **Add to marked items** as probe candidates.
- Past searches are reopenable; deleting a running search cancels it.

Extractor / search skills live in `skills/` (`02` single-email extractor, `03` idea search). Research context is database-backed.

### Admin

Collapsible panels for priorities, past probes (manual / PDF / URL), artifacts (manual / URL), not-useful list, categories, live prompt preview, and LLM call logs. Changes apply to **new** newsletters only.

## Layout

```
backend/         FastAPI app, IMAP sync, extraction and search jobs, SQLite models
backend/tools/   maintenance commands (IMAP pull smoke test)
frontend/        Vite + React review UI
skills/          prompts
tests/           backend tests
data/            local DB, created at runtime (gitignored)
```

## Hosting on Railway

See [docs/RAILWAY.md](docs/RAILWAY.md) for Dockerfile-based deploy, volume setup, env vars, and uploading your local SQLite database.
