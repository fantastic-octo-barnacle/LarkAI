# Deployment: GitHub + Custom Domain

This document covers turning the repo into a public/private GitHub project and serving the site under a custom domain. Two options:

- **Option A - interactive backend** (recommended): the full Flask app on a small VPS / PaaS, custom domain, HTTPS. Supports login, task submit/cancel and email.
- **Option B - static snapshot**: GitHub Pages serving a read-only export (dashboard/timeline), useful as a mirror; note that OAuth callbacks, task mutations and email need the backend (Option A).

This repo is already published at **https://github.com/fantastic-octo-barnacle/LarkAI** (branch `main`, SSH remote `git@github.com:fantastic-octo-barnacle/LarkAI.git`). The static mirror URL will be `https://fantastic-octo-barnacle.github.io/LarkAI/` once Pages is enabled.

## 0. Launch the website

1. **Setup once**
   ```bash
   make setup        # python venv + deps + .env from .env.example (only if missing)
   make check        # prints a config checklist; every line should say OK
   ```
2. **Local dev**: set `FEISHU_MODE=mock` (offline demo) or fill the Feishu credentials (`FEISHU_APP_ID`/`_SECRET`/`_REDIRECT_URI`) for live data, then
   ```bash
   make run          # http://127.0.0.1:5000
   ```
   First live run: open the site → **Login** (Feishu OAuth) → **Sync** (admin) or wait for the auto-collect interval.
3. **Production** (two workers, persistent DB volume):
   ```bash
   docker build -t rmhub .
   docker run -d --name rmhub -p 8000:8000 --env-file .env -v /srv/rmhub/data:/app/data rmhub
   ```
   or without Docker:
   ```bash
   pip install -r requirements.txt
   gunicorn -b 0.0.0.0:8000 -w 2 --timeout 120 "rmtask.web.app:create_app()"
   ```
4. **Checks**: `make test`; open `/settings` for SMTP status and `/notifications` for email audit.

## 1. GitHub repository

1. Create a repository, e.g. `rm-task-hub` (private is fine), at `https://github.com/<org>/rm-task-hub`.
2. Push from this directory:
   ```bash
   git init
   git add -A
   git commit -m "feat: RoboMaster task & info hub"
   git remote add origin git@github.com:<org>/rm-task-hub.git
   git push -u origin main
   ```
3. Recommended `.gitignore` already excludes `.env`, `*.db`, `data/mock_state.json`, `venv` - never commit secrets.
4. Add CI (optional): GitHub Actions running `python -m unittest discover -s tests`.

## 2. Option A - Deploy the backend (Flask)

Any host that runs Python 3.10+ works; the app uses only Flask + requests + stdlib (SQLite/SMTP).

### A1. Docker (simplest on a VPS)

A production `Dockerfile` is included in this repo (gunicorn + Flask on `python:3.12-slim`), with `.dockerignore` keeping secrets/local artifacts out of the image.

```bash
docker build -t rmhub .
docker run -d --name rmhub -p 8000:8000 \
  --env-file .env -v /srv/rmhub/data:/app/data rmhub
```

Mount a volume at `/app/data` so `rmtask.db` and mock state survive restarts. Secrets live in `.env` (excluded by `.dockerignore`), which is loaded at runtime from `--env-file`.

### CI and static Pages

- `.github/workflows/ci.yml`: on every push/PR - installs deps, runs the full test suite, and smoke-tests the static export.
- `.github/workflows/pages.yml`: on push to `main` it exports the mock-mode snapshot to `site/` and deploys it to GitHub Pages (Settings → Pages → Source: GitHub Actions).


### A2. PaaS (Render / Railway / Fly.io)

1. Push the repo to GitHub.
2. New service: root dir `.`, build `pip install -r requirements.txt`, start `gunicorn -b 0.0.0.0:$PORT rmtask.web.app:create_app()`.
3. Add environment variables from `.env.example` (App ID/Secret, redirect URI, SMTP, `FLASK_SECRET_KEY`).
4. Attach a persistent disk / SQLite volume (e.g. `/app/data`) so `rmtask.db` and mock state survive restarts.

### A3. Custom domain + HTTPS

1. Buy a domain (e.g. `yourteam.dev`) at any registrar.
2. Point DNS at the host: `A rm.yourteam.dev -> <server IP>` (or use a CNAME to a platform like Render/Railway). For Cloudflare, create an `A`/`CNAME` record and enable the orange-cloud proxy.
3. Enable HTTPS with Let's Encrypt (VPS: `certbot --nginx -d rm.yourteam.dev`) or let the PaaS/caddy handle TLS automatically.
4. Update Feishu: 开发配置 → 安全设置 → 重定向 URL -> `https://rm.yourteam.dev/oauth/callback`, and set the web-app home URL to `https://rm.yourteam.dev/` (then publish a new app version + admin approval).
5. Update `.env` in production: `FEISHU_REDIRECT_URI=https://rm.yourteam.dev/oauth/callback`, `FEISHU_ADMIN_OPEN_IDS=...`, `FLASK_SECRET_KEY=<random>`, SMTP settings.

### A4. Operations

- **Scheduling collection**: cron / systemd timer running `python -m scripts.collect`, or press Sync in the UI.
- **Backups**: copy `data/rmtask.db` (SQLite WAL) regularly.
- **Logs**: `logs/` for CLI runs; gunicorn stdout for the web app.
- **Security**: run behind HTTPS only; never expose `FEISHU_APP_SECRET` or tokens to the browser; keep `data/` outside the repo.

## 3. Option B - GitHub Pages static snapshot

For a read-only mirror under `https://<org>.github.io/rm-task-hub/`:

1. Add a workflow `.github/workflows/pages.yml` that (on push/`workflow_dispatch`) installs requirements, runs `python -m scripts.collect`, renders the pages to `site/` (e.g. via a small static-export script using the same templates/JSON APIs), then uploads via `actions/upload-pages-artifact` and `actions/deploy-pages`.
2. Repository Settings → Pages → Source: GitHub Actions.
3. Custom domain: Settings → Pages → Custom domain -> `rm.yourteam.dev`, then add a `CNAME` (`rm.yourteam.dev` -> `<org>.github.io`) in DNS.

Limitation: GitHub Pages serves only static files, so task submit/cancel and OAuth callback need Option A. The static export is a snapshot of the dashboard/timeline after `collect`.

## 4. Suggested end state for the ultimate goal

1. GitHub repo: `rm-task-hub` (private) - code + docs in this repo.
2. Live site: `https://rm.yourteam.dev` on Docker/VPS or PaaS with HTTPS + Feishu web-app embedding.
3. Feishu app: 企业自建应用 with 网页应用 capability, redirect URL matching prod, scopes per `docs/FEISHU_SETUP.md`.
4. Cron collection + email notifications enabled.
5. Optional: GitHub Pages static mirror for the public-facing competition info.

## dashboard.herkules.dev (independent production deployment)

`.github/workflows/deploy.yml` tests, builds and publishes a Linux/amd64 image,
then deploys its immutable GHCR digest on every push to `main`. A manual dispatch
on `main` redeploys that revision. It changes only the `larkai` Compose project in
`~/larkai`; it never deploys the Herkules application stack.

The Herkules repository owns the one-time Caddy route, DNS and Cloudflare Access
application. LarkAI joins the existing `herkules_default` network as `larkai`, with
no published host port. The app verifies Cloudflare's signature, issuer, audience,
expiry and user identity on **every** request (including assets and APIs). Access
uses the existing Herkules team policy. Feishu OAuth is a separate **Connect Feishu**
step for user-scoped API permissions; Cloudflare identities are not Feishu open IDs
and do not automatically become app administrators.

GitHub environment **production** holds `DEPLOY_HOST`, `DEPLOY_USER`,
`DEPLOY_SSH_KEY`, and `DEPLOY_KNOWN_HOSTS`. Optional secret **LARKAI_ENV** contains
dotenv settings to merge into the server-owned `~/larkai/.env`. Unspecified keys
are preserved; an explicit `KEY=` clears a value. If absent, deploys retain that file.
Never commit that file or credentials. Populate the secret with the real Feishu
values from `.env.example`. Cloudflare and Flask settings are already provisioned
on the server and do not need to be copied into this secret. The complete server
configuration includes:

```dotenv
FEISHU_MODE=live
FEISHU_REDIRECT_URI=https://dashboard.herkules.dev/oauth/callback
FLASK_SECRET_KEY=<random stable secret>
CF_ACCESS_ISSUER=https://hxyulin.cloudflareaccess.com
CF_ACCESS_AUD=<terraform output dashboard_access_aud>
RM_AUTO_COLLECT_SECONDS=0
```

Add the callback URL to the Feishu application's allowlist. Set explicit
`FEISHU_ADMIN_OPEN_IDS` before enabling Feishu login. With no Feishu credentials,
the protected site serves an empty live dashboard; it does not seed demo tasks.
Collection is disabled until the app credentials, data source and user connection
are configured. For two Gunicorn workers use a single external collector schedule,
not the per-process background thread. SMTP is off unless explicitly configured.

`larkai_data` persists SQLite across releases. Each subsequent deployment takes a
consistent SQLite snapshot into `~/larkai/backups/` and retains the previous image
and Compose configuration. Failed startup restores that image/configuration;
database migrations are **not** reversed. To roll back manually:

```sh
cd ~/larkai
cp backups/compose.previous.yml incoming/compose.yml
cp backups/image.previous.env incoming/image.env
bash apply.sh
```

These on-host snapshots do not replace an off-host backup policy. The workflow
checks container health (origin rejects requests without Access tokens) and the
public Cloudflare login challenge. End-to-end team sign-in must be checked in a
browser with an authorized account.
