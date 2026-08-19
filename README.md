# AINews Scout

Local web app that pulls **AINews-labelled Gmail**, extracts **Genie probe candidates** with OpenAI, and lets you review, categorise, and mark them on your machine.

Each person clones the repo, runs it locally, and connects **their own Gmail**. Emails, probe ideas, and your marks live in a local SQLite database. Nothing is hosted and nothing is shared between users.

## What is stored where

| Data | Location |
| --- | --- |
| Emails, probe candidates, your marks, categories, job progress | `data/probe_scout.sqlite` (created on first run, gitignored) |
| OpenAI key, Gmail OAuth client id/secret, label | `.env` (gitignored) |
| Gmail refresh token | `data/gmail_token.json` and your OS keychain (gitignored) |

Nothing in `data/` or `.env` is ever committed.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node 20+
- An OpenAI API key
- A Google Cloud project that can create an **Internal** OAuth client (a Google Workspace org). Personal Gmail Cloud projects cannot use Internal consent.

## Setup

```bash
git clone https://github.com/zainab-abaid/AINewsScout.git
cd AINewsScout

cp .env.example .env
# Fill in OPENAI_API_KEY, GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET (see below)

./run_dev.sh
```

Then open [http://127.0.0.1:5173](http://127.0.0.1:5173). The API listens on `127.0.0.1:8000` only, so nothing is reachable from the network.

`run_dev.sh` creates the Python environment with `uv`, installs frontend packages on first run, and starts both servers. To run them separately:

```bash
uv sync
export PYTHONPATH="$PWD"
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

cd frontend && npm install && npm run dev
```

### `.env`

```
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4
OPENAI_REASONING_EFFORT=high
GMAIL_LABEL=AINews
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
```

High reasoning on long newsletters takes roughly 2–3 minutes per email. Lower `OPENAI_REASONING_EFFORT` to `medium` if you want faster, shallower extraction.

## Connect Gmail

Google does not let this app create an OAuth client for you. Someone in the Workspace org creates one **once** in Cloud Console, then every user puts the same client id and secret in their own `.env` and signs in as themselves.

### Steps already done - you do not need to do these unless the existing GCP project is deleted:

1. Sign in to [Google Cloud Console](https://console.cloud.google.com/) with a Workspace account in your organisation.
2. Create or select a project **in that organisation**. Internal OAuth is unavailable on a personal Gmail Cloud account.
3. APIs & Services → enable the **Gmail API**.
4. OAuth consent screen → user type **Internal**.
5. Credentials → Create credentials → OAuth client ID → **Web application**.
6. Add this authorised redirect URI, exactly:

   `http://127.0.0.1:8000/api/gmail/callback`

### Steps you need to execute:

7. Copy your client id and secret (provided separately) into `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` in `.env`.
8. Reload the app, click **Connect Gmail** in the header, and sign in as yourself.

The app requests read-only Gmail scope. The refresh token stays on the machine that clicked Connect; **Disconnect** in the header removes it locally without touching the Cloud client.

## Sync

1. Label the newsletters you care about in Gmail (`AINews` by default, configurable with `GMAIL_LABEL`).
2. Pick a date range in the app UI and click **Sync Gmail**.
3. The app downloads matching messages, then GPT extracts probe ideas from each one, which takes roughly 2–3 minutes per new email.
4. If the range was already extracted, you are asked whether to **skip** those emails or **overwrite** the earlier ideas. Overwriting deletes previous candidates and any marks on them.

You can keep reviewing while extraction runs, and reloading the page reattaches to a job that is still going.

The UI has two tabs: **Review** for working through the queue, and **Marked** for everything you kept.

## Review

- **Filters**: model ranking (high priority / strong / possible) and your own marks. Multi-select.
- **Categories**: switch categories on or off. Anything you have not switched off stays visible, including categories you add later.
- **+ Add new category…** on any card, or **New category name** in the Categories menu, saves immediately and is available on every other card without a reload.
- **Show unprocessed items only** is on by default. Items you marked important, shortlisted, or deleted move into the collapsed **Processed by you** section rather than leaving the page.
- **Mark Important** and **Shortlist for Probe** take one click, then offer a comment box. The comment is optional: **Skip** leaves it empty, `Cmd/Ctrl+Enter` saves, `Esc` closes.
- If the item has no category yet, that same dialog says **You forgot to add a category** and offers the dropdown, including **+ Add new category…**. The category saves as soon as it is picked, so it still sticks if you skip the comment.
- Marks are attributed so they stay distinguishable from the model's ranking: **Marked important by user** and **Shortlisted by user**.
- Excerpts keep the newsletter's links as short clickable labels. Clicking the email title opens the full newsletter as rendered Markdown and scrolls to the passage the excerpt came from, highlighted in yellow. The passage is found by word overlap rather than an exact string, so it still lands correctly when the model wrote its own lead-in or when the excerpt and the body format links differently.

## Marked

Everything you marked important or shortlisted, newest first, with your comments.

- **All marked / Important only / Shortlisted only**, plus the same **Categories** filter and a search box that also covers your comments.
- Comments are editable in place, each item shows the date you marked it, and the category can be changed or filled in from here too.
- Unmarking an item removes it from this tab but keeps the comment, so it is still there if you mark the item again.
- Items marked before this tab existed had no mark date, so they fall back to the date the item was extracted.

## Re-importing email bodies

Emails are stored as Markdown converted from the HTML part of the message, which is what gives the reader its headings, lists and links. Sync skips messages already in the database, so an email keeps whichever conversion was in place when it arrived: after the converter improves, older emails stay as they were. That is worth knowing because a body with no blank lines renders as one unbroken wall of text, and the jump-to-excerpt cannot find a paragraph to land on.

To bring stored emails up to the current conversion:

```bash
uv run python -m backend.tools.reimport_bodies --dry-run  # report what would change
uv run python -m backend.tools.reimport_bodies            # apply
```

It re-downloads each stored message and rewrites `body_md` only. Candidates, categories, marks and comments are untouched, and a message that fails to download keeps its existing body. Back up `data/probe_scout.sqlite` first if you want a way back.

## Tests

```bash
uv run pytest          # backend: link handling, categories, marks and comments, re-import, settings
cd frontend && npm test # UI filter logic, block parsing and excerpt matching
```

## Layout

```
backend/    FastAPI app, Gmail sync, extraction jobs, SQLite models
backend/tools/  maintenance commands (email body re-import)
frontend/   Vite + React review UI
skills/     extraction prompts (01 research context, 02 single-email extractor)
tests/      backend tests
data/       local DB and Gmail token, created at runtime (gitignored)
```

The extraction behaviour lives in `skills/`, not in the Python code. Edit `skills/02_single_email_candidate_extractor.md` to change what counts as a candidate, and `skills/01_genie_research_context.md` to change the research priorities used for ranking.
