# RoboMaster Research Task & Info Hub

A modular repo that collects RoboMaster Research team information from **Feishu** (tasks, group-chat messages, meetings/calendar), summarizes the timeline and important updates, and presents everything through a dedicated **interactive website**: dashboard, timeline, task board (submit / cancel / complete), email notifications, and JSON APIs. It is live-first: with `FEISHU_MODE=live` every task action is ported to Feishu (task API / Bitable), and a background auto-collect keeps the site fresh. Mock mode (`FEISHU_MODE=mock`) runs fully offline for development.

## Launch the website

### Option A — demo offline (no Feishu credentials needed)

```bash
make setup                       # venv + deps + copies .env.example -> .env (if missing)
make check                       # prints a configuration checklist
make run                         # http://127.0.0.1:5000
```

Set `FEISHU_MODE=mock` in `.env` to run fully offline with an empty local state (dashboard, timeline, task board all work; task actions stay local in `data/mock_state.json`).

### Option B — real Feishu data (recommended)

1. `make setup`, then open `.env` and set:
   - `FEISHU_MODE=live`
   - `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_REDIRECT_URI` (create the app per [docs/FEISHU_SETUP.md](docs/FEISHU_SETUP.md))
   - `FEISHU_BITABLE_APP_TOKEN` (or `FEISHU_WIKI_NODE_TOKEN`) + `FEISHU_BITABLE_SUBMIT_TABLE_ID` to submit tasks into the 任务管理表
   - `FEISHU_ADMIN_OPEN_IDS` (empty = first login becomes admin)
2. `make check` until it prints `LAUNCH READY`, then `make run`.
3. Open `http://127.0.0.1:5000` → click **Login** (Feishu OAuth; if you see `state mismatch`, retry in a fresh tab) → click **Sync** (admin) or wait for auto-collect (`RM_AUTO_COLLECT_SECONDS`) to load chats/meetings/tasks/Bitable rows into the timeline and task board.

### Production (Docker / gunicorn)

```bash
docker build -t rmhub .
docker run -d --name rmhub -p 8000:8000 --env-file .env -v /srv/rmhub/data:/app/data rmhub
# or: gunicorn -b 0.0.0.0:8000 -w 2 --timeout 120 "rmtask.web.app:create_app()"
```

Keep `FLASK_SECRET_KEY` random, serve behind HTTPS, and mount `/app/data` so `rmtask.db` persists. Full VPS/PaaS/custom-domain steps: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

### Utilities

```bash
make test           # unit + integration tests
python -m scripts.collect       # CLI collection + digest
python -m scripts.collect --notify / make notify   # email an important-items digest (deduped)
make export         # static snapshot to site/
python -m scripts.fetch_team_emails --limit 8      # cache member emails (needs contact scopes)
```

### Troubleshooting

- `/notifications` shows `dry_run` → SMTP not configured; add `SMTP_*` (see [docs/EMAIL_NOTIFICATIONS.md](docs/EMAIL_NOTIFICATIONS.md)).
- Sync unavailable → you are not admin; set `FEISHU_ADMIN_OPEN_IDS` or log in as the first user.
- No chats/tasks appear → re-login after granting new scopes; the bot/user token scope is listed in [docs/FEISHU_SETUP.md](docs/FEISHU_SETUP.md).

## What the website shows

- **Dashboard** (`/`): team/competition facts and milestones, live stats (pending / in progress / completed / overdue), next deadlines, latest important updates, upcoming events.
- **Timeline** (`/timeline`): every task deadline, group message and meeting merged into one time-ordered feed, importance-ranked, filterable by source and keyword, with a default-on **Omit overdue** toggle.
- **Task board** (`/tasks`): Feishu task-v2 tasks are interactive (create / complete / cancel / delete through the Feishu API); Bitable records are mirrored (status 待执行/执行中/已完成, priority, ddl and owners) and can be completed/cancelled once `base:record:update` is granted.
- **Members**: the assignee picker is fed from the cached Feishu directory (org users + group members, including externals); toggle selection with search and a temp-save text block, refreshed via **⟳ Members** (admin) or `python -m scripts.fetch_members`. The dashboard team-member list has the same toggle / search / temp-save toolkit.
- **Workload** (`/workload`): per-individual workload derived from the task board — active / pending / done / urgent / overdue counts, next deadline, division, and the member's task list.
- **Notifications** (`/notifications`): audit trail of every task-change email (delivered / dry-run / failed).
- **Settings** (`/settings`): notification recipients, SMTP status, run mode.
- **JSON APIs**: `/api/stats.json`, `/api/timeline.json`, `/api/team.json`, `/api/members.json` for further integration.

The background auto-collect (`RM_AUTO_COLLECT_SECONDS`) also emails the important digest automatically; `make notify` does the same on demand (both dedupe against `last_digest_ts`).

## Key design decisions

- **Provider abstraction** (`rmtask/providers.py`): `LiveProvider` for the real Feishu OpenAPI, `MockProvider` for an offline demo. Everything else is provider-agnostic.
- **Tokens stay server-side** and are cached/refreshed (tenant token in memory; user tokens in SQLite with refresh via `offline_access`).
- **task-v2 facts** (verified against official docs): list = `GET /open-apis/task/v2/tasks?type=my_tasks`; create body = `summary`/`description`/`due`/`members`/`client_token`; patch body = `{task, update_fields}` and completion is `completed_at` (ms); there is **no `priority`** field in task-v2, so priority is kept local and shown on the site.
- **Email notifications** never block the website: delivery failures are recorded in the DB audit trail.

## Repository layout

```text
rmtask/                main package (modular)
  api/                 Feishu OpenAPI wrappers (auth, tasks, im, calendar, wiki, bitable)
  collector/           collection pipeline, timeline + digest summarizer
  storage/             SQLite persistence (tasks mirror, users, tokens, events, notifications)
  notify/              SMTP emailer + task-change notification service
  web/                 Flask app (routes, templates, static)
  providers.py         LiveProvider / MockProvider abstraction
data/                  runtime database (git-ignored)
scripts/collect.py     CLI collector
scripts/fetch_members.py  fetch + cache the full member directory
tests/                 smoke tests (run: python -m unittest discover -s tests)
docs/                  setup, collection, interactive, email, deployment docs
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — modules, data flow, DB schema
- [docs/FEISHU_SETUP.md](docs/FEISHU_SETUP.md) — app creation, credentials, scopes, publish
- [docs/COLLECTION.md](docs/COLLECTION.md) — what is collected and how to schedule it
- [docs/INTERACTIVE_TASKS.md](docs/INTERACTIVE_TASKS.md) — website ↔ Feishu task API mapping
- [docs/EMAIL_NOTIFICATIONS.md](docs/EMAIL_NOTIFICATIONS.md) — email setup and events
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — GitHub repo + custom domain / hosting process

## Repository

- GitHub: <https://github.com/fantastic-octo-barnacle/LarkAI> (branch `main`, SSH remote)
- Production: `https://dashboard.herkules.dev/` (Herkules OIDC; Feishu is connected separately).
- The deploy workflow runs tests and deploys independently. Separate CI and Pages workflows are disabled.

## Tests

```bash
python -m unittest discover -s tests -v
```

`tests/test_smoke.py` covers the mock flow (dashboard render, login + sync, task create / cancel / complete with notification audit, digest, JSON APIs); `tests/test_live_api.py` locks the Feishu API contract with mocked HTTP (OAuth v3 URLs, task create/patch/list bodies, IM `msg_type` and seconds-based timestamps, calendar seconds).

### Sign-in and Feishu feature access

Production signs users in through Herkules and displays their name. Dashboard,
timeline and workload pages show shared team data without requiring a personal
Feishu connection. Opening Tasks (or using sync, diagnostics or member refresh)
requires a connected Feishu account. The page offers **Connect Feishu**, then
returns to the requested page after authorization. Existing connections are
reused; expired tokens are refreshed or lead back to the connection prompt.
Task submissions are never replayed automatically after authorization.

Herkules owns admin roles. Feishu authorization stays in LarkAI for now and is
linked to the immutable Herkules subject, never matched by email. Only the
requested feature is gated; declining Feishu access keeps dashboard access.
