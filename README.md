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
- An OpenAI API key that you will paste in .env.
- A Google Cloud project that can create an **Internal** OAuth client (a Google Workspace org). Personal Gmail Cloud projects cannot use Internal consent.

## Setup

```bash
git clone https://github.com/zainab-abaid/AINewsScout.git
cd AINewsScout

cp .env.example .env
# Fill in OPENAI_API_KEY, GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET

./run_dev.sh
```

Then open [http://127.0.0.1:5173](http://127.0.0.1:5173). The API listens on `127.0.0.1:8000` only, so nothing is reachable from the network.

`run_dev.sh` creates the Python environment with `uv`, installs frontend packages on first run, and starts both servers.


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

1. Label the newsletters you care about in Gmail with the label `AINews`. To label, follow the instructions in the "Label Your Emails" section below.
2. Pick a date range in the app UI and click **Sync Gmail**.
3. The app downloads matching messages, then GPT extracts probe ideas from each one, which takes roughly 2–3 minutes per new email.
4. If the range was already extracted, you are asked whether to **skip** those emails or **overwrite** the earlier ideas. Overwriting deletes previous candidates and any marks on them.

You can keep reviewing while extraction runs, and reloading the page reattaches to a job that is still going.

### How to Label AINews Emails:

1. Open Gmail in a desktop browser.
2. In the Gmail search bar, click the Show search options icon on the right.
3. In the From field, enter:
swyx+ainews@substack.com
4. Click Create filter. Gmail lets you create filters based on sender and other search criteria.
5. On the next screen:
   Check Apply the label
   Select AINews
   If the label does not exist yet, choose New label… and create AINews
   Check Also apply filter to matching conversations — this applies the label to the existing emails that match the sender.
6. Click Create filter.

From now on, Gmail will automatically apply the AINews label to new emails from swyx+ainews@substack.com, while the “also apply” option takes care of the existing matching emails.

## How the UI Works

The UI has three tabs: **Important items extracted from emails** for working through the queue, **Review marked items** for everything you kept, and **Search for ideas** for asking a question across whole newsletters.

Emails are permanent. Once a message is synced it stays in `data/probe_scout.sqlite` for good: sync skips anything already stored, and nothing in the app deletes an email. Overwriting an extraction replaces that email's probe ideas, never the email itself, which is why a search can still read newsletters from months ago.

## Important items extracted from emails

- **Filters**: model ranking (high priority / strong / possible) and your own marks. Multi-select.
- **Categories**: switch categories on or off. Anything you have not switched off stays visible, including categories you add later.
- **+ Add new category…** on any card, or **New category name** in the Categories menu, saves immediately and is available on every other card without a reload.
- **Show unprocessed items only** is on by default. Items you marked important, shortlisted, or deleted move into the collapsed **Processed by you** section rather than leaving the page.
- **Mark Important** and **Shortlist for Probe** take one click, then offer a comment box. The comment is optional: **Skip** leaves it empty, `Cmd/Ctrl+Enter` saves, `Esc` closes.
- If the item has no category yet, that same dialog says **You forgot to add a category** and offers the dropdown, including **+ Add new category…**. The category saves as soon as it is picked, so it still sticks if you skip the comment.
- Marks are attributed so they stay distinguishable from the model's ranking: **Marked important by user** and **Shortlisted by user**.
- Excerpts keep the newsletter's links as short clickable labels. Clicking the email title opens the full newsletter as rendered Markdown and scrolls to the passage the excerpt came from, highlighted in yellow. The passage is found by word overlap rather than an exact string, so it still lands correctly when the model wrote its own lead-in or when the excerpt and the body format links differently.

## Review marked items

Everything you marked important or shortlisted, newest first, with your comments.

- **All marked / Important only / Shortlisted only**, plus the same **Categories** filter and a search box that also covers your comments.
- Comments are editable in place, each item shows the date you marked it, and the category can be changed or filled in from here too.
- Unmarking an item removes it from this tab but keeps the comment, so it is still there if you mark the item again.
- Items marked before this tab existed had no mark date, so they fall back to the date the item was extracted.

## Search for ideas

Extraction asks the same question of every email ("what could become a probe?"). This tab asks *your* question instead, across whole newsletters rather than the excerpts already pulled out of them:

> List all the studies and papers mentioned in the emails that conclude that harnesses affect how well models perform on tasks in different benchmarks.

Type the question, optionally narrow the date range, and click **Search emails**. If the range goes farther back (or forward) than what is already stored, the search lists Gmail first and **downloads only the missing issues**. Anything already in the database is skipped — there is no re-download. Newly pulled emails stay in the database permanently, same as a Sync. Then every email in the range is read, so this finds passages that keyword search misses: a paragraph reporting that scores moved when the agent scaffold changed answers the question above even if it never says "harness".

How it runs:

- Gmail is checked for the date range. Already-stored Gmail ids are skipped; only missing messages are fetched. Connect Gmail first if you want a range that is not already on disk.
- Emails are packed into batches of four, capped by a character budget so an unusually long issue splits instead of crowding the context. Twelve newsletters is three batches of roughly 60,000–80,000 tokens each.
- Each batch goes to the same model and reasoning effort as extraction, with the batch and your question, and comes back with quoted passages plus a note on why each one bears on the question.
- Batches run one after another and results are saved as each one returns, so findings appear while the search is still going. Reloading or switching tabs reattaches to a search in progress.
- A batch that fails is counted and skipped rather than losing the rest of the search.
- Expect roughly 1–3 minutes per batch. The panel shows a Gmail download if needed, then which batch is being read and how many findings have landed.

Results look like the review cards: the email title opens the full newsletter and scrolls to the quoted passage, and links inside the quote are preserved even when the model dropped them.

- **Direct answer** means the passage answers the question on its own terms. **Related** means it is genuinely useful but incomplete — the right study without its conclusion, or a claim without a number — and the commentary says what is missing.
- Filter by relevance, or search within the findings.
- **Add to marked items** on a finding turns it into a probe candidate: you pick High priority / Strong / Possible (the same ranking the extractor uses), assign a category, optionally comment on why it is probe-worthy, and mark it important and/or shortlist it. It then appears in **Important items extracted from emails** and in **Review marked items**, even if the original extraction never surfaced that passage. If the quote already exists as a candidate, that card is reused rather than duplicated.
- Past searches are kept and listed under the box, with their findings, so you can reopen or delete them.
- Deleting a search that is still running stops it. The batch already with the model finishes, then nothing further is sent, so this is also how you cancel a search you did not mean to start.
- If the model call fails, the panel shows the reason the API gave — "You have no credits remaining", a rate limit, and so on — rather than a raw error dump.

What the model is told to do lives in `skills/03_idea_search_over_emails.md`: quote verbatim from the batch, never invent evidence, attribute every quote to the right email, prefer a borderline find over silence, and return nothing at all when the emails do not answer the question.

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
uv run pytest          # backend: link handling, categories, marks and comments, re-import, idea search
cd frontend && npm test # UI filter logic, block parsing, excerpt matching, search results
```

## Layout

```
backend/    FastAPI app, Gmail sync, extraction and search jobs, SQLite models
backend/tools/  maintenance commands (email body re-import)
frontend/   Vite + React review UI
skills/     prompts (01 research context, 02 single-email extractor, 03 idea search)
tests/      backend tests
data/       local DB and Gmail token, created at runtime (gitignored)
```

The model's behaviour lives in `skills/`, not in the Python code. Edit `skills/02_single_email_candidate_extractor.md` to change what counts as a candidate, `skills/01_genie_research_context.md` to change the research priorities used for ranking, and `skills/03_idea_search_over_emails.md` to change how the search judges and quotes evidence.
