# AINews Scout

Local web app that pulls **AI News newsletters from a dedicated inbox**, extracts **Genie probe candidates** with OpenAI, and lets you review, categorise, and mark them on your machine.

Each person clones the repo and runs it locally. Emails, probe ideas, and your marks live in a local SQLite database. Nothing is hosted and nothing is shared between users.

## What is stored where

| Data | Location |
| --- | --- |
| Emails, probe candidates, your marks, categories, job progress | `data/probe_scout.sqlite` (created on first run, gitignored) |
| OpenAI key, IMAP inbox credentials | `.env` (gitignored) |

Nothing in `data/` or `.env` is ever committed. Historic emails already in the database stay there permanently — sync only adds new messages.

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

The UI has three tabs: **Important items extracted from emails**, **Review marked items**, and **Search for ideas**.

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

Prompts live in `skills/` (`01` research context, `02` single-email extractor, `03` idea search).

## Layout

```
backend/         FastAPI app, IMAP sync, extraction and search jobs, SQLite models
backend/tools/   maintenance commands (IMAP pull smoke test)
frontend/        Vite + React review UI
skills/          prompts
tests/           backend tests
data/            local DB, created at runtime (gitignored)
```
