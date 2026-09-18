# Architecture

The repo is a Python package (`rmtask`) split into small, independently testable modules. The same code path serves both real Feishu data and an offline demo thanks to the provider abstraction.

## Module map

```text
rmtask/
  config.py        Environment settings (Settings dataclass) + .env loader
  errors.py        RmTaskError / FeishuAPIError / AuthError / ProviderError
  providers.py     BaseProvider, LiveProvider (Feishu), MockProvider (empty offline state)
  api/
    base.py        FeishuClient: HTTP + Bearer auth + paged list_all() + transient-failure retry
    auth.py        AuthManager: tenant token cache, OAuth v3 authorize/exchange/refresh, user_info
    tasks.py       task-v2: list / get / create / patch / complete / delete (doc-verified)
    im.py          im-v1: chats + message history -> normalized records
    calendar.py    calendar-v4: calendars + events -> meeting records
    wiki.py        wiki-v2: resolve a wiki node token (feishu.cn/wiki/<token>) -> obj_token/app_token
    bitable.py     bitable-v1: tables, record search, record create/update (website task writes)
  collector/
    pipeline.py    collect_all(): pull tasks/messages/meetings/bitable, mirror Bitable tasks, prune stale data, build digest
    summarizer.py  timeline_rows(), compute_stats(), build_digest(), compute_workload(), member_names()
    team.py        derive_team_info(): real groups/members/divisions from collected data
    members.py     fetch_all_members(): directory + group-chat members (incl. externals) -> users table
  storage/
    db.py          SQLite helpers (users, oauth_tokens, tasks, events, notifications, settings)
    models.py      TaskRecord / EventRecord / UserRecord / TokenRecord
  notify/
    emailer.py     SMTP delivery (stdlib), returns dry_run | sent | raises
    service.py     notify_task_change(): record + email + audit trail
  web/
    app.py         create_app(), template filter `dt`, per-request wiring
    routes.py      dashboard / timeline / tasks / workload / oauth / notifications / settings / JSON APIs
    templates/     server-rendered pages
    static/        style.css, app.js
tests/
  test_smoke.py    mock end-to-end flow
  test_live_api.py Feishu API contract (HTTP mocked; no credentials needed)
```

## Data flow

1. **Collect** (`scripts/collect.py` or web button *Sync*): `collect_all()` asks the provider for tasks, group-chat messages, calendar events and Bitable records, normalizes everything to `TaskRecord` / `EventRecord`, upserts into SQLite, mirrors Bitable records onto the task board and prunes rows no longer present (live mode). It also stores derived team facts (`team_live` setting) for the dashboard.
2. **Summarize**: the `EventRecord` list becomes the timeline (sorted, importance-ranked); `compute_stats()` yields pending/completed/overdue counts and next deadlines; `build_digest()` merges stats, latest important items and upcoming events for the dashboard.
3. **Serve**: Flask renders pages from SQLite; the provider is only consulted on explicit actions (sync, create, cancel, complete, delete).
4. **Mutate**: create/cancel/complete/delete call the provider first (Feishu API in live mode, JSON state in mock mode), then `upsert_task()` mirrors the result into SQLite, then `notify_task_change()` records an email notification.

## SQLite schema

```text
users(open_id PK, name, email, avatar_url, is_admin)
oauth_tokens(open_id PK, access_token, refresh_token, expires_at, refresh_expires_at, scope)
tasks(guid PK, title, description, due, priority, status, owner_open_id, owner_name,
      creator, url, source, created_at, updated_at)
events(id PK, source, source_id, title, description, ts, author, url, importance, tags, raw)
notifications(id PK, created_at, kind, subject, body, recipients, status, error)
settings(key PK, value)
```

`events` is upserted on `(source, source_id)` so repeated syncs do not duplicate the timeline. `tasks.guid` matches the Feishu task GUID; `priority` is local-only (task-v2 has no priority field).

## Provider contract

```python
class BaseProvider:
    get_team_info() -> dict
    list_tasks(open_id="") -> list[TaskRecord]
    create_task(payload, open_id="") -> TaskRecord
    update_task(guid, fields, open_id="") -> TaskRecord
    cancel_task(guid, open_id="") -> TaskRecord
    complete_task(guid, open_id="") -> TaskRecord
    delete_task(guid, open_id="") -> None
    collect_messages(open_id="") -> list[EventRecord]
    collect_meetings(open_id="") -> list[EventRecord]
    collect_bitable(open_id="") -> list[EventRecord]
```

- `LiveProvider`: user token from `oauth_tokens` (auto-refresh with `refresh_token`), tenant token as fallback app identity.
- With `FEISHU_BITABLE_SUBMIT_TABLE_ID` set, `create_task()` POSTs to the Bitable submit table; with `FEISHU_BITABLE_TASKS_TABLE_ID` set, Cancel/Complete on `source=bitable` tasks PATCH their status column (wrappers in `api/bitable.py`). Without these, the same methods use task-v2.
- `MockProvider`: offline demo; starts empty and persists tasks/messages/meetings in `data/mock_state.json` (git-ignored), so no sample data is bundled.

## Adding a new source

1. Add a wrapper under `rmtask/api/` or extend an existing one.
2. Add a `collect_*()` method to both providers returning `EventRecord`s.
3. Call it in `collector/pipeline.py::collect_all()`.
4. Extend `tests/test_smoke.py` (or add a test file) with in-test data for the new source.
