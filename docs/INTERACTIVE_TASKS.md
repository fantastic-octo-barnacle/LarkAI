# Interactive Task Management (website -> Feishu API)

The website is not a read-only mirror: users submit, complete and cancel tasks from the browser, and every action is ported to the Feishu task-v2 API / Bitable in live mode (`FEISHU_MODE=live`). In mock mode the same flow runs against `RM_MOCK_DATA_DIR/mock_state.json` so the whole interaction can be demonstrated offline. The “New task” form offers a team-member picker (names + open_ids derived from mirrored Bitable records, also exposed as `/api/members.json`) instead of asking for a raw open_id.

**Creation is resilient**: when Bitable create fails (missing `base:record:create`, field-type mismatch, or network), the provider automatically falls back to the Feishu task-v2 API, so submissions always succeed. The same client layer retries transient network errors 3x with backoff and surfaces them as a friendly error instead of a 500.

**Creation mirrors the Bitable “任务管理表：任务创建（组长）” form**: title, 兵种类型 (single-select), 研发组别 (multi-select), 优先级 (clamped to 高/中/低), ddl, 负责人 (person field → `[{"id": open_id}]`), 任务需求 / description, 备注. Select options are fetched from the base field properties and cached 5 minutes (falls back to built-in defaults when the API is unavailable). New records are written with 任务状态（由技术组长验收）= `待执行` (`FEISHU_BITABLE_DEFAULT_STATUS`) so they appear in the 组长 view, which hides records with an empty status. Naive `datetime-local` values are interpreted as the server's local timezone (Asia/Hong_Kong) for `ddl`.

## Task sources on the board

- **Feishu task-v2** (`source=feishu`): the interactive tasks - submitted, completed, cancelled and deleted from the website, then written back to the task-v2 API.
- **Bitable** (`source=bitable`): the team's 多维表格 records (e.g. 任务管理表 / 任务提交表格) are mirrored onto the board. To make the website manage them, set `FEISHU_BITABLE_SUBMIT_TABLE_ID` (new tasks POST to this table) and/or `FEISHU_BITABLE_TASKS_TABLE_ID` (Complete/Cancel PATCH the status column, Delete uses DELETE) in `.env`, and grant the `base:record:create` + `base:record:update` + `base:field:read` user scopes (publish + re-login; `base:record:delete` additionally enables self-service record deletion). Column names can be overridden with `FEISHU_BITABLE_NAME_FIELD` / `_DESC_FIELD` / `_DDL_FIELD` / `_PRIORITY_FIELD` / `_OWNER_FIELD` / `_STATUS_FIELD` (defaults match the RoboMaster base).

  If the configured submit table is a **form-responses table** (fields `Text` / `Submitted on` / `Respondents`, e.g. a 飞书表单 response sheet), the website detects this and writes the new task into the `Text` cell as a readable block (title, description, ddl, priority, assignee) instead of the column mapping - the record then appears as a form response.

## Authentication used

- Task actions run with the **user** identity: the `user_access_token` stored for the logged-in user (auto-refreshed with `refresh_token`).
- If the user has no token yet (e.g. collection via CLI), the **tenant** token is used as the app identity. With a tenant token, the task belongs to the app; assign the team lead's open_id to keep tasks visible to humans.
- Login flow: `GET /login` -> Feishu authorize page -> `GET /oauth/callback` -> tokens persisted in `oauth_tokens`.

## Website action -> Feishu API mapping

| Website action | Route | Feishu call | Body / notes |
|---|---|---|---|
| New task | `POST /tasks/new` | `POST /open-apis/task/v2/tasks` | `{summary, description?, due?: {timestamp, is_all_day}, members: [{id, type: user, role: assignee}], client_token}` |
| Cancel task | `POST /tasks/<guid>/cancel` | `PATCH /open-apis/task/v2/tasks/:task_guid` | `{task: {completed_at: "<now ms>"}, update_fields: ["completed_at"]}`; local status becomes `cancelled` |
| Complete task | `POST /tasks/<guid>/complete` | `PATCH /open-apis/task/v2/tasks/:task_guid` | Same patch with `completed_at`; local status `completed` |
| Edit task (future) | `POST /tasks/<guid>/edit` | `PATCH /open-apis/task/v2/tasks/:task_guid` | `{task: {summary?, description?, due?}, update_fields: ["summary", ...]}` - `update_fields` is required |
| Delete task (admin) | `POST /tasks/<guid>/delete` | `DELETE /open-apis/task/v2/tasks/:task_guid` | Soft-truth: keep local audit trail via notifications before deleting |
| Sync | `POST /sync` | list + im + calendar | `collect_all()` pulls everything back into SQLite |

With Bitable write config enabled, the same routes instead call the bitable-v1 API:

| Website action | Feishu call | Body |
|---|---|---|
| New task (Bitable) | `POST /open-apis/bitable/v1/apps/:app_token/tables/:submit_table_id/records` | `{fields: {任务名称, 备注, ddl: <ms>, 优先级, 负责人}}` |
| Complete / Cancel (Bitable) | `PUT /open-apis/bitable/v1/apps/:app_token/tables/:tasks_table_id/records/:record_id` | `{fields: {任务状态（由技术组长验收）: "已完成" / "已取消"}}` |

Create/update wrappers live in `rmtask/api/bitable.py` (`create_record` / `update_record`); the payload-to-columns mapping is `_bitable_task_fields()` in `rmtask/providers.py`.

Contract details implemented in `rmtask/api/tasks.py` (verified against official docs):

- **List** returns `data.items` (not `data.tasks`) and only "my tasks" (`type=my_tasks`).
- **Create** is idempotent when `client_token` (10-100 chars) is provided; a new UUID is generated per create.
- **Patch** requires a `task` wrapper object plus `update_fields` listing exactly the changed fields. Omitting a field listed in `update_fields` clears it.
- **Completion state** is `completed_at` (ms string); `"0"` restores a task to not-completed. There is no `completed: true` boolean in task-v2.
- **No priority field** exists in task-v2, so priority (`NORMAL`/`HIGH`/`URGENT`) is local-only metadata stored in the `tasks` table and rendered on the site.
- Members use `{id, type: "user", role: "assignee" | "follower"}` (the creator is set by the API).

## Error handling

- API errors are raised as `FeishuAPIError` (code + msg) or `ProviderError` and shown to the user as a flash message; the DB is only updated after the provider call succeeds, so the site never claims success after a failed Feishu call.
- Scope problems surface as `20027` (authorize) or `99991679` with `permission_violations` (API call) - re-check `docs/FEISHU_SETUP.md` section 4.
- Refresh failures fall back to a normal login page (`/login`).

## Email notifications after each action

Every create / cancel / complete / delete action calls `notify_task_change()` (see `docs/EMAIL_NOTIFICATIONS.md`): an email is sent to the configured recipients and the attempt is always recorded in the `notifications` table (sent / dry_run / failed).
