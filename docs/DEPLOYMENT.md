# Deployment: GitHub + Custom Domain

This document covers turning the repo into a public/private GitHub project and serving the site under a custom domain. Two options:

- **Option A - interactive backend** (recommended): the full Flask app on a small VPS / PaaS, custom domain, HTTPS. Supports login, task submit/cancel and email.
- **Option B - static snapshot**: GitHub Pages serving a read-only export (dashboard/timeline), useful as a mirror; note that OAuth callbacks, task mutations and email need the backend (Option A).

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

- `.github/workflows/ci.yml`: on every push/PR - installs deps, runs the 14 tests, and smoke-tests the static export.
- `.github/workflows/pages.yml`: deploys the `site/` snapshot to GitHub Pages.


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
