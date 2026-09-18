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

The standalone CI and Pages workflows were removed. `deploy.yml` runs the full
test suite before publishing and deploying the app. No Pages site is published.


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

The Herkules repository owns the one-time Caddy route and DNS/Cloudflare Access
configuration. LarkAI owns its image, runtime environment and database. Native
Herkules OIDC handles the website identity and roles. Optional Cloudflare Access
remains an additional edge gate when `CF_ACCESS_ISSUER` and `CF_ACCESS_AUD` are set.

Configure the GitHub `production` environment with the OIDC and Feishu secrets
listed below. A `LARKAI_ENV` dotenv secret may supply additional runtime settings;
individual secrets override corresponding values. Missing values preserve the
server's existing `.env`. Example non-secret settings:

```dotenv
FEISHU_MODE=live
FEISHU_REDIRECT_URI=https://dashboard.herkules.dev/oauth/callback
OIDC_ISSUER=https://herkules.dev/auth
OIDC_CLIENT_ID=larkai
PUBLIC_ORIGIN=https://dashboard.herkules.dev
RM_AUTO_COLLECT_SECONDS=300
```

Provision a stable random `FLASK_SECRET_KEY`, `OIDC_CLIENT_SECRET`, and the Feishu
app credentials. Register both providers' callback URLs. Users first sign in
through Herkules; Tasks offers Feishu authorization only when needed. No personal
connection is required to view shared dashboard data. A deployment never links
existing Feishu users by matching their names or email addresses.

`RM_AUTO_COLLECT_SECONDS` controls the existing per-process collector. With multiple
Gunicorn workers it runs once per worker; a single collector schedule is preferable
for shared production sync. This feature does not change collection ownership or
notification behavior.

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
checks `/healthz` and the public authentication redirect. End-to-end team sign-in must be checked in a
browser with an authorized account.

### Individual GitHub secrets

Instead of `LARKAI_ENV`, the production environment (or repository) can hold
individual secrets named `FEISHU_APP_ID`, `FEISHU_APP_SECRET`,
`FEISHU_REDIRECT_URI`, `FEISHU_WIKI_NODE_TOKEN`, `FEISHU_BITABLE_APP_TOKEN`,
`FEISHU_BITABLE_SUBMIT_TABLE_ID`, `FEISHU_BITABLE_TASKS_TABLE_ID`,
`FEISHU_ADMIN_OPEN_IDS`, and `FEISHU_SCOPES`. Non-empty individual secrets
override the corresponding values in `LARKAI_ENV`; unspecified values on the
server are preserved. Run Deploy LarkAI after changing secrets.


## Herkules OpenID Connect

Production uses the confidential `larkai` client at `https://herkules.dev/auth`.
`OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` and `PUBLIC_ORIGIN` are
required by production Compose and can be set as individual GitHub environment
secrets. The exact callback is `https://dashboard.herkules.dev/oidc/callback`.
Authlib handles discovery, authorization code + S256 PKCE, state, nonce, and
signed ID token verification. Tokens are held in private server-side sessions
under `/app/data/sessions`; the browser gets a Secure, HttpOnly, host-only cookie.
Session expiry requires another code exchange (normally using the existing
Herkules login), rather than storing long-lived refresh tokens.

Each authenticated request fetches UserInfo and verifies its subject and role.
Only `role=admin` from Herkules authorizes sync, diagnostics, deletion and settings;
`FEISHU_ADMIN_OPEN_IDS` and local Feishu admin flags do not grant production roles.
Provider failure returns 503, disabled/invalid accounts are signed out, and role
changes take effect on the next request. Forms use session-bound CSRF tokens.

**Connect Feishu** is separate from website login. `/oauth/callback` stores the
Feishu connection against the authenticated Herkules `sub`. A Feishu account
cannot be linked to two Herkules accounts; names/emails never link identities.
No manual Open ID list or directory lookup permission is needed. The original
Feishu callback URI still needs to be allowlisted in the Feishu app.

Cloudflare Access remains configured during rollout; retiring it is a separate
infrastructure change. Cloudflare DNS/proxy stays enabled. `/healthz` returns only `{"ok":true}` without authentication.
