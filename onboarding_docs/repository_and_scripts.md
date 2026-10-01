# Repository and scripts

GitHub: [zainab-abaid/AINewsScout](https://github.com/zainab-abaid/AINewsScout). The working branch is `main`.

```
backend/                 FastAPI app
  main.py                App, CORS, static UI, startup
  config.py              Env vars and paths
  database.py            Engine, create_all, ALTER TABLE for old databases, seed
  db.py                  SQLModel tables
  schemas.py             Request and response models
  auth.py                Role tokens
  prompts.py             Loads skills and research context into extractor instructions
  routers/               HTTP routes (core, ops, search, admin)
  services/              IMAP, jobs, extract, idea search, research context, ingest
  seed/                  research_context_seed.json, used only when tables are empty
  tools/test_imap_pull.py
frontend/                Vite + React. UI is mostly src/App.tsx
  src/api.ts             Types and fetch wrappers
  src/dates.ts           Date defaults and validation
  src/filters.ts         Review-list filters
  src/search.ts          AI search progress helpers
  src/excerpt.ts         Excerpt matching helpers
  src/markdown.tsx       Newsletter body rendering
skills/                  LLM instructions. Editing these changes model behaviour
tests/                   pytest. Uses a temporary SQLite file, never data/probe_scout.sqlite
frontend/tests/          vitest
docs/RAILWAY.md          Host setup
onboarding_docs/         This guide
run_dev.sh               Local API + Vite
Dockerfile               Production image
railway.toml             Health check and single-writer deploy settings
pyproject.toml           Python deps (uv)
.env.example             Variable names. Copy to .env. Never commit .env
```

There is no `skills/01`. Research context used to be a markdown skill. It is now database rows composed by `research_context_markdown`.

## Commands

From the repo root, with [uv](https://docs.astral.sh/uv/) and Node 20+:

```bash
cp .env.example .env   # then fill secrets locally
./run_dev.sh           # http://127.0.0.1:5173  and  API on :8000
uv run pytest
cd frontend && npm test && ./node_modules/.bin/tsc -b
uv run python -m backend.tools.test_imap_pull          # IMAP dry run
uv run python -m backend.tools.test_imap_pull --store  # write new matches
```

`./run_dev.sh` creates `.venv` with `uv sync` if needed, installs frontend packages if needed, starts uvicorn with `--reload`, then `npm run dev`.

Production does not use `run_dev.sh`. The image runs:

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## Tests

`tests/conftest.py` points `backend.database.engine` at a temp file and inserts one email plus one candidate. Tokens in tests are the constants in that file, not your `.env`.

Backend tests worth knowing:

| File | Covers |
| --- | --- |
| `tests/test_auth_admin.py` | Roles, categories, probe date, research-context prompt |
| `tests/test_imap_filter.py` | Auto-forward headers match; Google’s confirmation mail does not |
| `tests/test_idea_search.py` | Search stays inside the database |
| `tests/test_marks.py` | Important / shortlist |
| `tests/test_categories.py` | Category assignment |
| `frontend/tests/dates.test.ts` | AI search default range and date errors |

## Frontend shape

`App.tsx` holds the lock screen, the four tabs, candidate cards, the marked-items review, AI search, and the whole admin panel. Shared pieces in that file include `ConfirmDialog`, `CommentPrompt`, `InfoTip`, and `JobProgress`.

Do not add a second state store. Server data is loaded in the tab and patched through `api.ts`. The access token is only in `sessionStorage`.

Date strings in the UI are `YYYY-MM-DD` in the viewer’s timezone (`todayISO` in `dates.ts`). The server’s future-date check allows through tomorrow UTC so an Australian evening is not rejected.
