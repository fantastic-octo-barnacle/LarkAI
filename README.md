# RoboMaster Research Task & Info Hub

A modular repo that collects RoboMaster Research team information from **Feishu** (tasks, group-chat messages, meetings/calendar), summarizes the timeline and important updates, and presents everything through a dedicated **interactive website**: dashboard, timeline, task board (submit / cancel / complete), email notifications, and JSON APIs. It is live-first: with `FEISHU_MODE=live` every task action is ported to Feishu (task API / Bitable), and a background auto-collect keeps the site fresh. Mock mode (`FEISHU_MODE=mock`) runs fully offline for development.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # FEISHU_MODE=live is the default once credentials are set
python run.py                   # http://127.0.0.1:5000
python -m scripts.collect       # optional CLI collection + digest
python -m scripts.collect --notify   # email an important-items digest (deduped since the last digest)
make run / make test / make collect / make export   # shortcuts (see Makefile)
```

Open `http://127.0.0.1:5000`, click **Login** (Feishu OAuth), click **Sync** (admin), or wait for the background auto-collect to load real tasks/chats/meetings into the timeline and task board.

## Switching to real Feishu data

1. Follow [docs/FEISHU_SETUP.md](docs/FEISHU_SETUP.md) to create an app and get `App ID` / `App Secret` / scopes.
2. Set `FEISHU_MODE=live` plus `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_REDIRECT_URI` in `.env`.
3. Log in through the website (OAuth v3), then run **Sync** (or `python -m scripts.collect`).

## What the website shows

- **Dashboard** (`/`): team/competition facts and milestones, live stats (pending / in progress / completed / overdue), next deadlines, latest important updates, upcoming events.
- **Timeline** (`/timeline`): every task deadline, group message and meeting merged into one time-ordered feed, importance-ranked, filterable by source and keyword.
- **Task board** (`/tasks`): Feishu task-v2 tasks are interactive (create / complete / cancel / delete through the Feishu API); Bitable records are mirrored (status 待执行/执行中/已完成, priority, ddl and owners) and can be completed/cancelled once `base:record:update` is granted.
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
tests/fixtures/        sample JSON used only by mock-mode tests
scripts/collect.py     CLI collector
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
- Static mirror: `https://fantastic-octo-barnacle.github.io/LarkAI/` once GitHub Pages is enabled

## Tests

```bash
python -m unittest discover -s tests -v
```

`tests/test_smoke.py` covers the mock flow (dashboard render, login + sync, task create / cancel / complete with notification audit, digest, JSON APIs); `tests/test_live_api.py` locks the Feishu API contract with mocked HTTP (OAuth v3 URLs, task create/patch/list bodies, IM `msg_type` and seconds-based timestamps, calendar seconds).
