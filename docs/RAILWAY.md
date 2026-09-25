# Deploy on Railway

This app runs as **one service**: FastAPI serves the API and the built React UI.
SQLite lives on a **Railway Volume** (not in GitHub).

Official docs used for this setup:

- [Dockerfiles](https://docs.railway.com/guides/dockerfiles)
- [Volumes](https://docs.railway.com/guides/volumes)
- [Config as code](https://docs.railway.com/reference/config-as-code)
- [CLI volume files](https://docs.railway.com/guides/cli) (`railway volume …`)

---

## Before you start (on your Mac)

1. Make the GitHub repo **private**.
2. Commit and push `main` (includes `Dockerfile`, `railway.toml`, viewer-token support).
3. In local `.env`, set all three tokens (do this yourself; never commit `.env`):

```env
VIEWER_TOKEN=...
ANALYST_TOKEN=...
ADMIN_TOKEN=...
```

4. Confirm your database file exists:

```bash
ls -lh data/probe_scout.sqlite
```

5. Optional local check that Docker builds:

```bash
docker build -t ainews-scout .
```

---

## Exact Railway steps

### A. Create the project from GitHub

1. Sign up / log in at [railway.app](https://railway.app).
2. **New Project** → **Deploy from GitHub repo**.
3. Authorize GitHub if asked; pick **AINewsScout** (private is fine).
4. Railway creates a service and starts a build from the root `Dockerfile`.
5. Open the service → **Settings** → **Networking** → **Generate Domain**  
   (you get something like `https://….up.railway.app`).

### B. Attach a volume for SQLite (required)

1. In the project canvas, **right-click** (or `⌘K`) → **Add Volume**.
2. Connect it to your web service.
3. Set **Mount Path** to exactly:

```text
/app/data
```

   That matches `DATA_DIR=/app/data` in the Dockerfile.  
   Railway docs: if the app writes to `./data`, mount `/app/data`.

4. Size: **1 GB** is enough to start (you can live-resize later on Hobby/Pro).

5. Redeploy if the first deploy finished before the volume existed  
   (**Deployments** → **Redeploy**).

### C. Set environment variables (Variables tab)

Copy the same secrets you use locally. At minimum:

| Variable | Notes |
| --- | --- |
| `OPENAI_API_KEY` | Required for extract / search / ingest |
| `OPENAI_MODEL` | e.g. `gpt-5.4` |
| `OPENAI_REASONING_EFFORT` | e.g. `high` |
| `IMAP_HOST` | `imap.gmail.com` |
| `IMAP_PORT` | `993` |
| `IMAP_USER` | Dedicated inbox address |
| `IMAP_PASSWORD` | App password (no spaces) |
| `IMAP_FOLDER` | `INBOX` |
| `IMAP_ALLOWED_FROM` | Your forwarder address |
| `IMAP_SYNC_ENABLED` | `1` |
| `IMAP_SYNC_HOUR` | Hour **in the server timezone (UTC on Railway)** e.g. `20` ≈ 6am AEST |
| `VIEWER_TOKEN` | Required so the public URL cannot be scraped |
| `ANALYST_TOKEN` | Analyst unlock |
| `ADMIN_TOKEN` | Admin unlock |
| `DATA_DIR` | Optional; Dockerfile already sets `/app/data` |

Do **not** put `.env` in GitHub. Paste values only in Railway’s Variables UI.

`PORT` is set by Railway automatically — do not override it.

### D. Upload your existing database (one-time)

The empty volume starts with no SQLite file. Copy your local DB onto the volume.

**Option 1 — Railway CLI (recommended)**

```bash
# Install CLI: https://docs.railway.com/guides/cli
npm i -g @railway/cli
railway login
cd /path/to/topic_extraction_from_AINews
railway link   # pick the project + service

# Upload local DB to the volume mount
railway volume files upload ./data/probe_scout.sqlite /probe_scout.sqlite
```

Because the volume is mounted at `/app/data`, the file path **on the volume** is often shown relative to the mount root. If the CLI expects paths under the mount, use:

```bash
railway volume files upload ./data/probe_scout.sqlite ./probe_scout.sqlite
# or browse first:
railway volume browse
```

Then **restart** the service so it opens the uploaded file.

**Option 2 — If CLI upload path is confusing**

1. `railway volume browse` and upload `probe_scout.sqlite` so it ends up as `/app/data/probe_scout.sqlite` inside the container.
2. Restart the service.

Confirm after restart: sign in with your **viewer** token and check that candidates appear.

### E. Verify

1. Open the Railway public URL.
2. You should see the **locked** gate (not free content).
3. Enter `VIEWER_TOKEN` → browse.
4. Switch role → `ANALYST_TOKEN` / `ADMIN_TOKEN` as needed.
5. Check **Deployments** logs for `Application startup complete` and no SQLite errors.
6. Daily IMAP sync runs while the service is up, at `IMAP_SYNC_HOUR` **UTC**.

---

## Important Railway settings (already in repo)

`railway.toml` sets:

- `overlapSeconds = 0` — only one container touches the SQLite file during deploy  
- `healthcheckPath = /api/health`  
- Dockerfile builder  

Keep **replicas = 1**. SQLite is not safe with multiple writers.

---

## What not to do

- Do not commit `data/probe_scout.sqlite` or `.env`.
- Do not use Render-style “sleep when idle” free tiers if you need daily sync.
- Do not scale this service horizontally.
- Do not rely on a secret URL without `VIEWER_TOKEN`.

---

## Updating the app later

Push to `main` → Railway rebuilds from the Dockerfile.  
The **volume keeps the database** across deploys.  
Back up occasionally: download the sqlite file with `railway volume files download`.
