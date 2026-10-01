# Deploy on Railway from scratch

Use this when **nothing is deployed yet**: no Railway project, or you are intentionally creating a new one. The app that is already live is described in [inbox and login tokens](inbox_and_login_tokens.md). Do not create a second project for that service. Pushing `main` updates the existing one.

This app is one container. FastAPI serves the API and the built React UI. SQLite is a file on a Railway volume, not in GitHub.

## What you need first

1. A [Railway](https://railway.app) account.
2. The GitHub repo [zainab-abaid/AINewsScout](https://github.com/zainab-abaid/AINewsScout) on `main`. It must stay **private**. `Dockerfile` and `railway.toml` are already in the repo. Railway builds from the Dockerfile. You do not pick a start command in the dashboard.
3. A local `.env` filled from `.env.example`, including `OPENAI_API_KEY`, the IMAP settings, and all three role tokens. Generate tokens with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

4. If you want the new host to have the existing newsletters and marks, the file `data/probe_scout.sqlite` on your machine. If you skip the upload, the app creates an empty database and seeds research context from `backend/seed/research_context_seed.json`. That is a blank app, not a copy of production.

Optional check that the image builds:

```bash
docker build -t ainews-scout .
```

## 1. Create the project

1. In Railway, **New Project** → **Deploy from GitHub repo**.
2. Authorize GitHub if asked, and select **AINewsScout**.
3. Railway creates one service and starts a build. The first deploy can finish before the volume and variables exist. That is expected. You will redeploy after those are in place.
4. Open the service → **Settings** → **Networking** → **Generate Domain**. You get a URL like `https://something.up.railway.app`.

Leave **replicas at 1**. `railway.toml` already sets `overlapSeconds = 0` so an old container and a new one never write the same SQLite file. Do not scale horizontally.

## 2. Add one volume

SQLite must live on a volume or it is wiped on every deploy.

1. On the project canvas, add a volume and attach it to this service.
2. Set the mount path to exactly:

```text
/app/data
```

The Dockerfile sets `DATA_DIR=/app/data`, so the database file inside the container is `/app/data/probe_scout.sqlite`.

3. 1 GB is enough to start.
4. A service can have **only one volume**. If a deploy error says the service would have two volumes, delete the extra one. Do not add a second volume to “fix” an upload.

If the first deploy finished before the volume existed, open **Deployments** and redeploy after the volume is attached.

## 3. Set variables, then apply them

Open the service → **Variables**. Paste the same values as local `.env`. Do not commit `.env`.

| Variable | Value |
| --- | --- |
| `OPENAI_API_KEY` | Your OpenAI key |
| `OPENAI_MODEL` | `gpt-5.4` unless you have a reason to change it |
| `OPENAI_REASONING_EFFORT` | `high` |
| `IMAP_HOST` | `imap.gmail.com` |
| `IMAP_PORT` | `993` |
| `IMAP_USER` | Dedicated inbox address |
| `IMAP_PASSWORD` | Gmail app password, no spaces |
| `IMAP_FOLDER` | `INBOX` |
| `IMAP_ALLOWED_FROM` | The forwarder address that must appear in From or the forward headers. See [inbox and login tokens](inbox_and_login_tokens.md). |
| `IMAP_SYNC_ENABLED` | `1` |
| `IMAP_SYNC_HOUR` | Hour `0–23` in **UTC**. `6` means 06:00 UTC (16:00 AEST). |
| `VIEWER_TOKEN` | Required. If this is empty, anyone who can open the URL is a viewer. |
| `ANALYST_TOKEN` | Analyst unlock |
| `ADMIN_TOKEN` | Admin unlock |

Do not set `PORT`. Railway injects it. Do not set `DATA_DIR` unless you changed the volume mount. The image already sets `/app/data`.

Variables you type are only a **draft** until you click **Apply changes**. A **Redeploy** by itself uses the last applied set. After you apply, wait until the new deployment is successful.

## 4. Upload the existing database

Skip this only if you want an empty app.

Install and log in to the CLI: [Railway CLI](https://docs.railway.com/guides/cli).

```bash
npm i -g @railway/cli
railway login
cd /path/to/the/repo
railway link
```

`railway link` must select this new project and its service.

### Register an SSH key

Volume file commands fail with “No SSH keys found” until Railway has a public key.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_railway -N ""
railway ssh keys add --key ~/.ssh/id_ed25519_railway.pub --name your-machine-name
```

### Find the volume id

```bash
railway volume list
```

“Available options can not be empty” on a volume command means the service has **no volume**. Go back to step 2. Do not create a second volume if one is already attached.

### Upload

`--volume` belongs on `railway volume files`, not on `upload`.

The path you pass is **inside the volume**, and the volume is mounted at `/app/data`. Uploading to `/probe_scout.sqlite` becomes `/app/data/probe_scout.sqlite` in the container.

```bash
railway volume files --volume VOLUME_ID upload ./data/probe_scout.sqlite /probe_scout.sqlite --overwrite
```

Replace `VOLUME_ID` with the id from `railway volume list`. If the CLI says the file already exists, you omitted `--overwrite`.

Restart the service after the upload so the process opens that file.

To copy the file back off the volume later:

```bash
railway volume files --volume VOLUME_ID download /probe_scout.sqlite ./probe_scout.backup.sqlite
```

## 5. Check that it worked

1. Open the generated URL. You should see the lock screen, not the newsletter list.
2. `https://YOUR-DOMAIN/api/auth/status` should include `"viewer_token_set": true`, `"analyst_token_set": true`, and `"admin_token_set": true`. If any flag is false, the variable was not applied.
3. Sign in with the viewer token. Candidates from the uploaded database should be there. An empty list means the upload missed the file or the app created a new database before the volume was mounted.
4. In **Deployments** logs, look for `Application startup complete` and an `IMAP sync` line. There should be no SQLite “unable to open database” error.
5. Sign in as analyst and use **Sync inbox now** only if you want a live mail pull. The daily sync also runs at `IMAP_SYNC_HOUR` UTC while the service is up.

A shell on the container must use `uv run python`. The image’s system `python` does not have the app’s packages.

## 6. Later changes

Push to `main`. Railway rebuilds and deploys. The volume, and therefore the database, stays.

Changing a variable still requires **Apply changes**.

Before a risky schema change, download the sqlite file with the command in step 4.

## Do not

- Commit `.env` or `data/probe_scout.sqlite`.
- Attach two volumes to the service.
- Set replicas above 1.
- Leave `VIEWER_TOKEN` empty on a public URL.
- Detach the volume to “reset” the app. That hides the real corpus. An empty volume seeds the research-context JSON and looks like a fresh install.
- Put the app on a host that sleeps when idle if you need the daily inbox pull. The pull only runs while the process is up.
