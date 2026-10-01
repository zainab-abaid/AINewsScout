# Architecture

## What the running system is

Locally, two processes run:

- Vite on `http://127.0.0.1:5173` proxies `/api` to the API.
- Uvicorn on `http://127.0.0.1:8000` serves FastAPI.

On Railway there is one process. The Docker build compiles the React app into `frontend/dist`, and FastAPI serves that build plus `/api`. Same-origin, so the browser does not need CORS for production.

Startup is `backend/main.py` `lifespan`:

1. `init_db()` creates tables, adds any missing columns, and seeds research context if the tables are empty.
2. `resume_orphaned_jobs()` continues extract or search jobs that were running when the process died.
3. `start_imap_daily_sync()` pulls the inbox once, then again every day at `IMAP_SYNC_HOUR`.

## Roles

`backend/auth.py` maps the `X-Access-Token` header to `locked`, `viewer`, `analyst`, or `admin`. The browser stores the token in `sessionStorage` under `ainews_access_token` (`frontend/src/api.ts`). It is not a user account system. Three shared secrets are the whole access model.

If `VIEWER_TOKEN` is empty, a request with no token is treated as a viewer. That is a local convenience. Production sets `VIEWER_TOKEN`, so the public URL shows a lock screen until someone pastes a token.

Rank is viewer < analyst < admin. `require_role("analyst")` allows analyst and admin.

## Data

SQLite file: `data/probe_scout.sqlite` locally, `/app/data/probe_scout.sqlite` on Railway (`DATA_DIR`).

| Table | Purpose |
| --- | --- |
| `emails` | One stored newsletter. Body is Markdown in `body_md`. `extraction_status` is `pending`, `running`, `done`, or an error. |
| `candidates` | One extracted probe idea from one email: tag, topic, main idea, excerpt, category, important, shortlisted, notes, `marked_at`. |
| `categories` | Taxonomy. `deprecated` hides a category from new extractions. Old candidates keep it. |
| `jobs` | In-process background work for sync, extract, and AI search. Progress is JSON. |
| `idea_searches` / `idea_search_hits` | A question, its date range, and quoted findings. `candidate_id` is set when someone keeps a hit. |
| `research_probes` | Past Genie probes shown to the extractor. `probe_date` is `YYYY-MM-DD`. |
| `research_artifacts` | Related Genie work that was not a numbered probe. |
| `research_priorities` | Higher-priority research areas. |
| `research_not_useful` | Topics the extractor should ignore. |
| `llm_call_logs` | Prompt and response for extract, search, and ingest calls. Admin-only. |
| `settings` | Leftover key/value table. Research context no longer lives here. |

Models are SQLModel classes in `backend/db.py`. Sessions go through `backend/database.py` `session_scope`.

## Jobs

There is no Celery or Redis. `backend/services/jobs.py` runs work on daemon threads inside the API process. Kinds are sync, extract, and idea search. The UI polls `GET /api/jobs/active` and `GET /api/jobs/{id}`.

Only one active job is expected. A deploy or crash marks in-flight work so startup can resume it.

## LLM calls

All model calls use the OpenAI Responses API via the `openai` SDK.

| Call | Code | Prompt source |
| --- | --- | --- |
| Extract candidates from one email | `backend/services/extract.py`, driven by `jobs.extract_email_ids` | `skills/02_single_email_candidate_extractor.md` plus the research-context markdown from `research_context.py`, composed in `backend/prompts.py` |
| AI search over a batch of emails | `backend/services/idea_search.py` | `skills/03_idea_search_over_emails.md` |
| Turn a URL, PDF, or pasted text into a probe or artifact blurb | `backend/services/content_ingest.py` `summarise_source` | Instructions are in that file, not in `skills/` |

Model and reasoning effort come from `OPENAI_MODEL` and `OPENAI_REASONING_EFFORT` in `backend/config.py`. Search batches default to 4 emails or 320,000 characters (`IDEA_SEARCH_EMAILS_PER_CHUNK`, `IDEA_SEARCH_CHUNK_CHARS`).

Every call can be written to `llm_call_logs`.

## Mail versus search

`backend/services/imap_sync.py` `fetch_and_store` is the only IMAP download. It is used by:

- the startup and daily sync thread
- `POST /api/sync` (**Sync inbox now**)

`run_idea_search_job` does not call it. `preview_search` reports `will_fetch: 0`.

After new messages are stored, `run_imap_sync_once` calls `extract_email_ids` when `OPENAI_API_KEY` is set. Manual sync does the same for new and still-pending emails.

## API map

Routers are mounted at `/api` in `backend/main.py`.

| Router | Responsibility |
| --- | --- |
| `backend/routers/core.py` | Candidates, one email body, categories, stats |
| `backend/routers/ops.py` | Jobs, sync, extract, settings status |
| `backend/routers/search.py` | AI search preview, create, poll, delete, keep a hit |
| `backend/routers/admin.py` | Auth unlock, research context, probe/artifact ingest, LLM logs |

`GET /api/health` is the Railway health check.
