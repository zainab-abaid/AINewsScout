# Start here before changing the app

Start here if you are changing AINews Scout and have no prior context. The app is a private FastAPI + React tool. It pulls AI News newsletters from a dedicated Gmail inbox, asks an LLM to extract Genie probe candidates, and lets people review, mark, search, and edit the research context those extractions use.

Production is already live. Pushing `main` deploys it. The database is a single SQLite file on a Railway volume, not in Git. Read [inbox and login tokens](inbox_and_login_tokens.md) before you touch secrets or mail. Read [deploy on Railway from scratch](deploy_on_railway_from_scratch.md) only if you are creating a new host.

The folder index is [README.md](README.md).

## Read next

| Doc | What it answers |
| --- | --- |
| [How the running app is structured](how_the_running_app_is_structured.md) | Request path, roles, jobs, database, prompts |
| [Folder layout and commands](folder_layout_and_commands.md) | Where files live and which commands to run |
| [Where each feature is implemented](where_each_feature_is_implemented.md) | Each product feature and the files that implement it |
| [Inbox and login tokens](inbox_and_login_tokens.md) | The connected inbox, role tokens, and the live server |
| [Deploy on Railway from scratch](deploy_on_railway_from_scratch.md) | Create the host when nothing is deployed yet |
| [README](../README.md) | Clone, `.env`, and `./run_dev.sh` |

## Rules that are easy to break

- **Do not commit** `.env`, `data/`, or `*.sqlite`. Secrets live in local `.env` and in Railway Variables.
- **Do not run more than one app process against the production database.** SQLite has one writer. Railway is configured for a single replica.
- **AI search does not read Gmail.** Only the daily sync and **Sync inbox now** pull mail. Search reads rows already in `emails`.
- **Admin edits do not re-extract old newsletters.** Research context and categories affect the next extraction only. Marks and comments stay.
- **New columns on an existing table need two edits.** SQLModel `create_all` does not alter a table that already exists. Add the field on the model in `backend/db.py` and add an `ALTER TABLE` entry in `backend/database.py` `_add_missing_columns`. Production already has a database, so the alter is what Railway will run.
- **The UI is one file.** Almost every screen is `frontend/src/App.tsx`. API types and fetch helpers are `frontend/src/api.ts`.

## How to add a feature

1. Find the feature in [where each feature is implemented](where_each_feature_is_implemented.md) and start from those files.
2. If the change is user-visible, update the React screen and the matching function in `api.ts`.
3. If the change is stored, update `backend/db.py`, `backend/schemas.py`, and the router. If the table already exists in production, also update `_add_missing_columns`.
4. If the change affects what the extractor or AI search believes, edit `skills/02_…` or `skills/03_…`, or the research-context composer in `backend/services/research_context.py`. Those files are the prompt. They are not documentation.
5. Add or extend a test under `tests/`. Frontend date logic has tests in `frontend/tests/`.
6. Run `uv run pytest` from the repo root and, for UI or `api.ts` changes, `npm test` and `./node_modules/.bin/tsc -b` inside `frontend/`.
7. Push to `main` only when the change should go live. Railway rebuilds from the Dockerfile and keeps the volume.

## What “done” means on this codebase

A behaviour change is not done when only the UI copy changes. Trace it through the router, the service, and the SQLite row. The production database is the user’s real newsletter corpus and marks. A bad migration or a sync that deletes mail would destroy that. The app never deletes stored newsletters.
