# Inbox and login tokens

Nothing in this file is a password or a role token. Those values are in local `.env` and in the Railway service variables. Do not copy them into Git.

## The inbox

The app logs into one dedicated Gmail account over IMAP and an app password.

| | |
| --- | --- |
| Address | `ainewsscout24@gmail.com` (`IMAP_USER`) |
| Host | `imap.gmail.com` port `993`, folder `INBOX` |
| Password | Gmail app password in `IMAP_PASSWORD`. Not the normal Gmail password. Spaces are stripped in `backend/config.py`. |
| Allow list | `IMAP_ALLOWED_FROM=zainab.abaid@emumba.com` |

Newsletters are not subscribed on that Gmail account directly. They arrive as forwards from the main mailbox. A typical original sender is `AINews <swyx+ainews@substack.com>`. Gmail auto-forward **keeps that original From**. The forwarding address shows up in `To`, `X-Forwarded-For`, and related headers.

Because of that, sync does **not** search IMAP with `FROM`. It `SEARCH ALL`, fetches headers, and keeps a message when `IMAP_ALLOWED_FROM` appears in any of:

`From`, `To`, `Cc`, `Sender`, `Delivered-To`, `Resent-From`, `X-Forwarded-For`, `X-Forwarded-To`

That logic is `headers_allowed` in `backend/services/imap_sync.py`. A Google forwarding-confirmation message does not match. Messages already stored (same RFC822 Message-ID or the same derived `imap:…` id) are not downloaded again. Stored newsletters are never deleted by sync.

`IMAP_SYNC_HOUR` is an hour on the **API process clock**, `0–23`. Railway containers use UTC. The live value is `6`, so the daily pull is **06:00 UTC**, which is **16:00 AEST** (Sydney standard time, UTC+10) and **17:00 AEDT**. Locally, the same value means 06:00 in the machine’s own timezone. The process also pulls once at startup.

`IMAP_SYNC_ENABLED=1` turns the thread on. If the user or password is missing, the thread logs that sync is not configured and does nothing.

Manual check from a machine that has the `.env`:

```bash
uv run python -m backend.tools.test_imap_pull
uv run python -m backend.tools.test_imap_pull --store
```

## Role tokens

Three shared secrets. Generate a new one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

| Env var | Role | Can |
| --- | --- | --- |
| `VIEWER_TOKEN` | viewer | Open the app, read candidates, marked items, and AI search |
| `ANALYST_TOKEN` | analyst | Viewer, plus marks, comments, categories that already exist, sync, extract, keep a search hit |
| `ADMIN_TOKEN` | admin | Analyst, plus the Admin tab |

The UI sends the pasted value as `X-Access-Token`. **Switch role** in the header replaces it. Sign-out clears `sessionStorage`.

Production has all three set. If `VIEWER_TOKEN` is empty, anyone who can reach the API is a viewer. Do not leave it empty on Railway.

An empty analyst or admin token means that role cannot be unlocked. `GET /api/auth/status` reports whether each token is set. It does not return the token values.

Rotating a token is a Railway variable change plus the same change in local `.env` if you still use it. People who had the old token stay locked until they paste the new one.

## Railway

| | |
| --- | --- |
| Live URL | https://ainewsscout-production.up.railway.app |
| GitHub | `zainab-abaid/AINewsScout`, branch `main` |
| Railway project | `chic-serenity` |
| Service | `AINewsScout` |
| Database | One volume mounted at `/app/data`. File inside the container: `/app/data/probe_scout.sqlite` |
| Health check | `GET /api/health` |
| Replicas | 1. `railway.toml` sets `overlapSeconds = 0` so two containers never write the same SQLite file |

Pushing `main` builds the Dockerfile and deploys. The volume survives deploys. An empty volume would boot a new database and seed research context from `backend/seed/research_context_seed.json`, which would hide the real corpus. Do not detach the volume.

### Changing variables

Railway keeps a drafted variable set until you click **Apply changes**. A plain **Redeploy** uses the last applied set. After apply, wait until the new deployment is successful, then hard-refresh the site. `GET /api/auth/status` should show the three `*_token_set` flags as `true`.

`PORT` is injected by Railway. Do not set it yourself. `DATA_DIR=/app/data` is set in the Dockerfile.

### Volume files

The CLI needs an SSH key registered with Railway (`railway ssh keys add`) before `railway volume files` works. Attach the `--volume` flag to `railway volume files`, not to the `upload` subcommand. One service can have only one volume. Do not add a second volume to get a clean upload. Uploading over the live database needs an explicit overwrite and a restart afterward.

Creating the host when none exists is [deploy on Railway from scratch](deploy_on_railway_from_scratch.md). Do not follow that guide against the live project unless you intend to replace it.

### What a bad deploy looks like

- Lock screen missing and content visible with no token: `VIEWER_TOKEN` is not applied.
- Site up, newsletter list stuck on an old date: sync failed, the allow-list missed auto-forwards, or extraction did not run. Check deploy logs for `IMAP sync` lines. App loggers only show INFO because `main.py` calls `logging.basicConfig`. A shell on the container needs `uv run python`, not the image’s system `python`, because dependencies live in the uv environment.
- Two volumes or a replaced volume: the service can fail to deploy, or it can come up with an empty database.

Back up the sqlite file with `railway volume files download` before a risky migration.
