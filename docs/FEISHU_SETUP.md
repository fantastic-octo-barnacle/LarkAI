# Feishu Setup

Everything below is verified against the current Feishu Open Platform docs. Account needed: a Feishu enterprise tenant (personal accounts cannot create apps).

## 1. Create the app

1. Open `https://open.feishu.cn/app` and sign in with the tenant admin account.
2. Click **创建企业自建应用** (custom app). For internal team use, custom app is the right choice; store/ISV apps are only for selling to other tenants.
3. Fill the basic info, then open **基础信息 → 凭证与基础信息** and copy the **App ID** (`cli_...`) and **App Secret**. Keep the secret server-side only.

## 2. Enable the web-app capability

1. Go to **应用能力** and enable **网页应用**.
2. Set the desktop/mobile home page URL to your deployed site (e.g. `https://rm.example.com/`) - required for the app to open inside the Feishu workbench.

## 3. Configure the OAuth redirect URL

1. Open **开发配置 → 安全设置 → 重定向 URL**.
2. Add exactly the callback URL used by this repo: `FEISHU_REDIRECT_URI` (default `http://127.0.0.1:5000/oauth/callback`; for production `https://your.domain/oauth/callback`).
3. Only URLs in this list pass the platform security check. Multiple URLs are allowed (e.g. localhost + production).

## 4. Request API scopes

Open **开发配置 → 权限管理 → API 权限** and request (then publish) the scopes the app needs:

| Feature | Scope | Notes |
|---|---|---|
| Login / user identity | `auth:user.id:read` | Required for `GET /open-apis/authen/v1/user_info` |
| See / manage tasks | `task:task:readonly` or `task:task:write` / `task:task:writeonly` | `write` also allows delete (`task:task:delete` works instead); `writeonly` covers create/update |
| Refresh tokens | `offline_access` | Required to receive a `refresh_token` |
| Group chat list + messages | `im:chat:readonly` + `im:message.group_msg:get_as_user` (user) or `im:message:readonly` / `im:message` (app/bot) | Reads as the logged-in user need the `get_as_user` scope (error 230027); app/bot path needs the bot added to each group |
| Meetings / calendar | `calendar:calendar:readonly` | For collecting meeting events |
| Bitable (your task database) | `base:table:read` + `base:record:retrieve` (read) plus `base:record:create` + `base:record:update` + `base:field:read` (website submit/cancel writes; `base:record:delete` for self-service deletion) | Reads use the logged-in user's token, so grant the `base:*` scopes; writes need `base:record:create` (POST / new tasks) and `base:record:update` (PATCH / complete-cancel) |
| Wiki (resolve wiki-hosted Bitable) | `wiki:wiki:readonly` (or `wiki:wiki` / `wiki:node:read`) | Needed to resolve a `feishu.cn/wiki/<token>` URL to the base's `app_token` |
| Drive / Docs (optional) | `drive:drive:readonly` | If you extend collection to files/docs |

> Note: if the authorize URL contains a scope the app has not been granted, the user sees error `20027`. If an API is called without the right scope, Feishu returns `99991679` with a `permission_violations` list.

## 5. Tokens used by this repo

- `tenant_access_token` (`t-...`): app identity. Fetched with App ID + App Secret and cached ~60 s before expiry.
- `user_access_token`: user identity, obtained with the OAuth v3 flow (authorize -> code -> token). Stored in `oauth_tokens` and refreshed automatically via `refresh_token`.

Endpoints as implemented in `rmtask/api/auth.py`:

```text
GET  https://accounts.feishu.cn/open-apis/authen/v1/authorize   (authorize page)
POST https://accounts.feishu.cn/oauth/v3/token                 (exchange + refresh)
GET  https://open.feishu.cn/open-apis/authen/v1/user_info
POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
```

The v3 token endpoint accepts `application/x-www-form-urlencoded` (recommended) or JSON. `user_access_token` expires after ~7200 s; `refresh_token` is single-use and the user must re-authorize after 365 days.

## 6. Environment variables

Copy `.env.example` to `.env` and fill:

```bash
FEISHU_MODE=live
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_REDIRECT_URI=https://your.domain/oauth/callback
FEISHU_SCOPES=auth:user.id:read task:task:read task:task:write im:chat:readonly calendar:calendar:readonly wiki:wiki:readonly base:table:read base:record:retrieve base:record:create im:message:readonly im:message.group_msg:get_as_user offline_access
# FEISHU_WIKI_NODE_TOKEN=WBJjwtT7TizbTekjBPMcMxT5nbe   # token from a feishu.cn/wiki/<token> URL (auto-resolved to app_token)
# FEISHU_BITABLE_APP_TOKEN=xxxxxxxx                     # or paste the app_token from a direct base URL (feishu.cn/base/<app_token>)
```

Optional: `FEISHU_CHAT_IDS` (limit message collection to specific chats), `FEISHU_CALENDAR_ID`, `FEISHU_ADMIN_OPEN_IDS` (open_ids allowed to sync/delete; when empty, the first user who logs in becomes admin).

Website task writes into Bitable (submit → `任务提交表格`, complete/cancel → `任务管理表`; needs `base:record:create` + `base:record:update` + `base:field:read`):

```bash
FEISHU_BITABLE_SUBMIT_TABLE_ID=tbl...
FEISHU_BITABLE_TASKS_TABLE_ID=tbl...
# optional column overrides (defaults match the RoboMaster base):
FEISHU_BITABLE_NAME_FIELD=任务名称
FEISHU_BITABLE_DESC_FIELD=备注
FEISHU_BITABLE_DDL_FIELD=ddl
FEISHU_BITABLE_PRIORITY_FIELD=优先级
FEISHU_BITABLE_OWNER_FIELD=负责人
FEISHU_BITABLE_STATUS_FIELD=任务状态（由技术组长验收）
# FEISHU_BITABLE_DEFAULT_STATUS=待执行   # value written on website-created records (required to show in the 任务创建（组长） view)

### Reading member emails

Member emails come from the contact directory:

    GET /open-apis/contact/v3/users/{open_id}?user_id_type=open_id

The response `user.email` / `user.enterprise_email` is populated once the app holds the directory scope AND the
email scope. The directory scope is
(`contact:contact.base:readonly`; the API also accepts `contact:contact:readonly` / `contact:contact:readonly_as_app` /
`contact:contact:access_as_app`); the email scope is `contact:user.email:readonly` (获取用户邮箱信息). Grant BOTH in
the developer console and publish the app version; add both to `FEISHU_SCOPES` and re-login for user-token reads.
Without the email scope the API returns `email: ""` (user token omits the field entirely).

Fetch + cache samples into the local `users` table:

    python -m scripts.fetch_team_emails --limit 8
```

The wiki URL's last path segment (`WBJjwtT7TizbTekjBPMcMxT5nbe`) is a **wiki node token**, not the Bitable `app_token`; the repo resolves it automatically via `GET /open-apis/wiki/v2/spaces/get_node` and reads the base with the returned `obj_token`.

## 7. Publish / review

Any change to basic info, permissions, capabilities or event subscription requires **发布新版本** in the developer console and the enterprise admin's approval before it takes effect. For testing, create a separate test enterprise (new tenant) where permission approval is automatic.

## 8. Data reachability reminder

- With a `user_access_token`, the app can only touch resources that (a) the app's approved scopes cover and (b) that specific user can access.
- With only a `tenant_access_token` (no user login), the app sees only what is granted to the app identity: bots need to be members of groups, Bitable bases need the app as collaborator, contact data needs the admin-configured data scope.
## 9. Troubleshooting: "no connection" to chats / tasks / data

The site shows sample data or a source is empty while Feishu has content? Diagnose in this order (also use the in-app **Diagnostics** page after admin login):

1. **Running against real Feishu?** Check `FEISHU_MODE=live` in `.env` - `mock` reads `RM_MOCK_DATA_DIR` (default `data/`) and never calls Feishu.
2. **Permissions granted, not just declared?** Feishu replies `Access denied. One of the following scopes is required: [...]` and includes a direct link to request each scope (e.g. `https://open.feishu.cn/app/<APP_ID>/auth?q=task:task:read,...`). Request every scope the app needs, then **publish a new app version** (发布) - permission changes only take effect after publishing plus enterprise-admin approval.
3. **Token type matches the source?**
   - `tenant_access_token` (CLI `scripts/collect.py` without `--open-id`, or Sync while the website user has no stored token): app identity. Group chats require the **bot capability enabled AND the bot added to the group**; tasks are only those assigned to the app.
   - `user_access_token` (login through the website first): user identity - reachable chats/tasks/calendars are the logged-in user's own, but group message history additionally needs `im:message.group_msg:get_as_user` (Feishu returns 230027 without it).
4. **Bot capability for IM?** `GET /im/v1/chats` returns error `232025 Bot ability is not activated` until the app has the **机器人** capability enabled (应用能力 → 添加应用能力 → 机器人) and a new version is published - even with a `user_access_token`.

5. **Wiki/Bitable still `99991679`?** The scope must exist in the login token: after granting/publishing scopes, log out of the site and log back in (a refresh token keeps the old scope set). Wiki nodes need `wiki:wiki:readonly`; Bitable needs `base:table:read` + `base:record:retrieve` under the user identity.
6. **App published and available to you?** The app must be released, approved, enabled, and you must be inside the app's 可用范围 (availability), otherwise login can fail (error 20010) or return no data.
7. **"Database" = Bitable?** Bitable is a separate capability: request `base:table:read` + `base:record:retrieve` (user) or `bitable:app:readonly` (app) and make sure the logged-in user is a collaborator on the base; our SQLite store is always local (`data/rmtask.db`) and mirrors whatever the API returns.
8. **Grant links are specific per API**: task-v2 -> `task:task:read`/`task:task:write`, im group info -> `im:chat:readonly`/`im:chat`, im group message history (user) -> `im:message.group_msg:get_as_user`, calendar -> `calendar:calendar:readonly`, wiki -> `wiki:wiki:readonly`, bitable -> `base:table:read` + `base:record:retrieve`.
