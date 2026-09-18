# Information Collection

`collect_all()` (implemented in `rmtask/collector/pipeline.py`) turns Feishu data into two local artifacts: a **task mirror** (`tasks` table) and a **timeline** (`events` table). Everything is fetched with the token of the logged-in user when available (falls back to the tenant/app token), so only data that identity is allowed to see is collected.

## What is collected

| Source | API | Normalized as | Notes |
|---|---|---|---|
| Tasks | `GET /open-apis/task/v2/tasks?type=my_tasks` | `EventRecord(source=task)` | Lists tasks the calling identity is responsible for; each task becomes a timeline item at its due time. |
| Group chats | `GET /open-apis/im/v1/chats` | chat list | Used to enumerate chats; restricted by `FEISHU_CHAT_IDS` when set. |
| Chat messages | `GET /open-apis/im/v1/messages?container_id_type=chat` | `EventRecord(source=message)` | Message text becomes description; sender is the author. |
| Meetings / calendar | `GET /open-apis/calendar/v4/calendars` + `.../events` | `EventRecord(source=meeting)` | Calendar events (e.g. weekly sync, strategy session). |
| Team info (groups / members / divisions) | derived from collected tasks + chat tags | Dashboard facts | `derive_team_info()` in `rmtask/collector/team.py`; no static mock profile. |

| Bitable (多维表格) | `GET .../apps/:app_token/tables` + `POST .../records/search` | `EventRecord(source=bitable)` + `TaskRecord(source=bitable)` | Configured per base: `FEISHU_BITABLE_APP_TOKEN` (from the base URL `feishu.cn/base/<app_token>...`) or `FEISHU_WIKI_NODE_TOKEN` (auto-resolves a wiki URL). Records become timeline items **and** are mirrored into the task board (title / ddl / status 待执行·执行中·已完成 / 优先级 / 负责人). |

Optional future sources: Drive/Docs (file list, docx, wiki) - endpoints are listed in `docs/FEISHU_SETUP.md`.

## Importance scoring

Each event gets an `importance` score (0-3):

- Tasks: 2 by default; 3 for `HIGH`/`URGENT`; 1 for completed tasks.
- Messages/meetings: 2-3 when the text matches important keywords (重要, 紧急, deadline, 截止, 比赛, 阻塞, 风险, milestone, release, etc.), otherwise 1.

The digest (`build_digest()`) then surfaces the latest important events and upcoming items on the dashboard.

## Running collection

```bash
# Web: click "Sync" on the site (admin only)
# CLI:
python -m scripts.collect                  # uses env settings
python -m scripts.collect --open-id ou_xxx # act as a specific user in live mode
python -m scripts.collect --notify         # email a digest of important items after collecting
```

The site also shows a **last-sync timestamp** in the header. Set `RM_AUTO_COLLECT_SECONDS` (e.g. `300`) to run `collect_all()` in a background loop on the web server (it reuses the latest stored user token). In production prefer a cron job over the in-process loop, which is single-process only.

Scheduling (production, e.g. every 15 minutes during the competition season):

```cron
*/15 * * * * cd /opt/rmhub && /opt/rmhub/.venv/bin/python -m scripts.collect >> /var/log/rmhub-collect.log 2>&1
```

## Stability & limits

- `events` upserts on `(source, source_id)`, so re-runs never duplicate items; a changed item is updated in place.
- In live mode the collector purges leftover `mock` tasks (from demo runs) and prunes Bitable tasks/events whose record no longer appears in the base, so the board mirrors reality.
- `list_all()` in `rmtask/api/base.py` follows `page_token`/`has_more` automatically (page size 50).
- Feishu messages API paginates by `create_time`; the collector keeps the default range and can be narrowed with `FEISHU_CHAT_IDS`.
- Task list API returns only "my tasks" for the calling identity; to collect the whole team's tasks the app needs each member to log in once (tokens are persisted and refreshed), or a tasklist shared with the app when using the tenant token.

## API conventions verified against the docs

- **Times**: task `due` is ms strings; IM `start_time`/`end_time` query params and calendar query params (`start_time`/`end_time`) plus calendar `time_info.timestamp` are **seconds**; IM `create_time` is ms. Wrappers in `rmtask/api/im.py` / `rmtask/api/calendar.py` follow this exactly.
- **IM message field**: the item key is `msg_type` (not `message_type`) and `content` is a serialized JSON string - see `message_text()`.
- **Pagination**: `data.items` + `page_token`/`has_more` for task list, messages and calendar events; `list_all()` in `rmtask/api/base.py` handles it.
- **Scopes for user-identity message reads**: `im:message.p2p_msg:get_as_user` / `im:message.group_msg:get_as_user` (plus `im:message` or `im:message:readonly`); app identity requires the bot to be in the group.
- **`im/v1/chats` always requires the bot capability** (error 232025) - enable 机器人 in 应用能力 and publish, even when using a `user_access_token`.
- `tests/test_live_api.py` locks all of the above with mocked HTTP - run `python -m unittest tests.test_live_api`.
