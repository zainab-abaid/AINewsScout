# Where each feature is implemented

The header tabs are declared at `TABS` in `frontend/src/App.tsx`. Admin is hidden unless the role is admin.

## Important items extracted from emails

The first tab. Lists `candidates` for stored newsletters.

Filters: model tag (high priority, strong, possible), important / shortlisted, category, and unprocessed. “Unprocessed” means not important and not shortlisted.

Analysts and admins can mark **Important** or **Shortlist**. The first time either is turned on from this tab, an in-app comment dialog opens. It is not a browser `window.prompt`. The important placeholder is “Why is this important?”. The shortlist placeholder is “Why is this worth a probe?”. Turning a mark off does not open it. The Review marked items tab does not open it.

Delete uses the in-app `ConfirmDialog`, not `window.confirm`.

The email title opens the Markdown body and scrolls to the excerpt. Links inside excerpts are kept.

| Piece | File |
| --- | --- |
| Cards, filters, comment dialog | `frontend/src/App.tsx` (`CandidateCard`, `CommentPrompt`) |
| List filters | `frontend/src/filters.ts` |
| Excerpt / link helpers | `frontend/src/excerpt.ts`, `frontend/src/markdown.tsx` |
| `GET/PATCH /api/candidates`, `GET /api/emails/{id}` | `backend/routers/core.py` |
| Mark fields | `candidates.important`, `shortlisted`, `notes`, `marked_at` |

`marked_at` is set when an item first becomes important or shortlisted, and cleared when both are removed. Items marked before that column existed were backfilled from `created_at` in `database.py`.

## Review marked items

Second tab. Same candidate rows, limited to important or shortlisted. The toolbar (filters plus keyword search) stays sticky while the list scrolls. The clear control is labelled **Clear filters**.

On this tab the button that clears Important says **Mark not important**. The card on the first tab still says **Unmark Important**.

## Sync inbox and extraction

**Sync inbox now** calls `POST /api/sync`. That job downloads new allowed messages, then extracts every new or still-pending email.

The daily thread does the same pull on startup and at `IMAP_SYNC_HOUR` (`backend/services/imap_scheduler.py`).

Extraction is one email per model call. Status lives on `emails.extraction_status`. Failures are stored on the email and in `llm_call_logs`. Re-running extract picks up `pending` and failed rows. It does not wipe marks on candidates that already exist.

Changing a skill or the admin research context does **not** re-run extraction. Someone must sync new mail or run extract again. Old candidates stay as they were.

## AI search

Third tab. The user types a question and a date range. The default range is the last 14 days inclusive (today and the 13 days before), clamped to newsletters actually stored. Dates in the future, or outside the oldest and newest stored newsletter, are rejected in the UI (`frontend/src/dates.ts`) and again in `validate_search_dates`.

The search reads `emails.body_md` for that range only. It does not call IMAP, even if the range is older than the newest mail. New mail appears in search only after a sync has stored it.

Implementation: `POST /api/searches` creates an `idea_searches` row and a job. `run_idea_search_job` splits emails into batches and calls the model one batch at a time. Hits are saved as each batch returns, so a failed batch does not drop earlier hits. The panel polls progress (a status line and a bar).

**Add to marked items** on a hit calls `POST /api/searches/{id}/hits/{hit_id}/keep`. If that excerpt already exists as a candidate on the same email, that candidate is reused. Otherwise a new candidate is inserted. Analyst role required.

Deleting a running search cancels it (`DELETE /api/searches/{id}`).

Past searches are listed from `GET /api/searches`.

## Admin

Fourth tab. Panels are collapsible. Nothing in this tab re-analyses mail already in the database.

### Higher-priority research areas

Collapsed row: name and **Edit**. Edit opens the name and description. **Save edits** sends `PATCH /api/admin/priorities/{id}`. **Delete area** is only inside the editor and uses `ConfirmDialog`.

### Previous Genie probes

Each row has an editable date. Probes with a date are listed newest first. Probes with no date stay at the bottom so older rows can be dated by hand. New probes added from the form get the browser’s current date (`todayISO`).

The add form accepts **one** of: pasted text, a URL, or a PDF. Submit sends that input to `summarise_source`, which stores an LLM-written title and short description. The raw paste is not the stored description. A URL contributes page text only (no images or video). The progress bar is only the in-flight HTTP call. There is no separate job row.

Endpoints: `POST /api/admin/probes/ingest-text`, `ingest-url`, `ingest-pdf`. `PATCH /api/admin/probes/{id}` updates title, description, and `probe_date`.

`POST /api/admin/probes` still creates a row directly. The UI does not expose that manual form.

The date is included in the extractor prompt as `Date: YYYY-MM-DD` when set (`research_context_markdown`).

### Related artifacts, not-useful, categories

Artifacts can be typed by hand or drafted from a URL. They have no probe date.

The not-useful list is short lines injected as bullets in the extractor prompt.

Categories can be added or deprecated. Deprecated categories remain on old candidates and are omitted from the category list sent to the next extraction.

### Prompt preview and LLM logs

The research-context panel can show the markdown block that will be appended to the next extraction. LLM logs are `GET /api/admin/llm-logs` and the detail route. They are how you see the exact prompt and model output after a run.

## Comments and confirms

Both are React components in `App.tsx`. Do not switch them to `window.confirm`, `window.prompt`, or `window.open`. Those were removed on purpose because browsers block or style them inconsistently.
