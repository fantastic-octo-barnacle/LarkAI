# Feishu Open Platform - API Credentials & Task-Management Website Feasibility

Research date: 2026-09-15. Sources: https://open.feishu.cn/document (doc markdown mirror), official `larksuite/oapi-sdk-go` service definitions, and Feishu developer-console docs.

## 1. Repo status - no API key present

The `ai_doc` repo is currently empty (only `.git`, `.agents`, `.codex`). No Feishu `App ID` / `App Secret` (or any other service credential) exists in this repo, the surrounding workspace, or environment variables. Nothing could be read from a file here.

For Feishu, the "API key" is not a single secret string in code; it is the **App ID + App Secret pair** obtained from the developer console and kept server-side.

## 2. The credential pair and how it is used

**Where to get the keys**
- Log in at https://open.feishu.cn/app ; you must belong to a Feishu enterprise tenant.
- Create/select the app, then open **基础信息 > 凭证与基础信息** (Credentials & Basic Info) and copy **App ID** and **App Secret**.
- App kinds: **企业自建应用** (custom app, internal use, reviewed by the enterprise admin) vs **商店应用** (ISV store app usable by other tenants).

**Access tokens (the actual auth used by APIs)**
- `tenant_access_token` - app-identity token (prefix `t-`), no user login needed.
  - `POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal` with JSON `{"app_id": "...", "app_secret": "..."}`.
  - Returns `tenant_access_token` plus `expire` (about 7200 s). Cache it server-side and refresh before expiry.
- `user_access_token` - user-identity token from the web-app OAuth flow:
  - Redirect the user to `https://passport.feishu.cn/suite/passport/oauth/authorize?client_id=APP_ID&redirect_uri=...&response_type=code&state=...`.
  - Exchange the returned `code` for the token. Add the callback URL to **开发配置 > 安全设置 > 重定向 URL** first.
- `app_access_token` - only for ISV/store apps (with `app_ticket`).

**How to call APIs**
- Every request carries `Authorization: Bearer <token>` and `Content-Type: application/json`.
- Call only from a **server**; never put tokens in a browser/frontend.
- Grant the required API permissions (权限管理) and extra field scopes for sensitive fields; optional IP allow-list.
- Publishing: any change (basic info, permissions, event subscription, web-app URLs) requires a new app version (发布) plus enterprise-admin approval before it takes effect.

## 3. Publishing a website - YES

Feishu natively supports a **网页应用 (web app)** capability:
- Enable the web-app capability and set desktop/mobile home URLs. An existing H5/business website then opens inside the Feishu workbench on desktop and mobile.
- OAuth web login (免登) lets Feishu users sign into your site with their Feishu account; a QR login SDK is also available.
- Web apps support server-side APIs and can also be distributed as store apps.
- Feishu does **not** host your site - you host it over HTTPS; Feishu embeds/links it and supplies auth plus APIs.

## 4. Task management - YES

Feishu Task API (`task-v2`) provides full task-management coverage (verified against the official SDK and docs):

| Capability | Endpoint | Required permission |
|---|---|---|
| Create / list / get / update task | `POST /open-apis/task/v2/tasks`, `GET /open-apis/task/v2/tasks`, `GET/PATCH /open-apis/task/v2/tasks/:task_guid` | `task:task:write` / `task:task:writeonly` |
| Subtasks | `/open-apis/task/v2/task-subtask/...` | `task:task:write` / read scopes |
| Task members, reminders, dependencies | `/open-apis/task/v2/tasks/:task_guid/add_members|add_reminders|add_dependencies` and remove variants | `task:task:write` |
| Tasklists / sections | `/open-apis/task/v2/tasklists`, `/open-apis/task/v2/sections` | `task:task:write` / read scopes |
| Comments and attachments | `/open-apis/task/v2/comments`, `/open-apis/task/v2/attachments` | `task:task:write` / read scopes |
| Custom fields | `/open-apis/task/v2/custom_fields*` | `task:task:write` |

Notes:
- Both Custom App and Store App are supported; `tenant_access_token` or `user_access_token` can be used.
- `GET /open-apis/task/v2/tasks` lists tasks where the calling identity is the assignee ("我负责的").
- Task authorization is per-task: a caller can read a task as creator/assignee/follower, via a group share, as a doc collaborator, list collaborator, or via a subtask chain; editing is limited to creator/assignee or editable collaborators.

## 5. Bottom line

**Yes - publishing a website for task management with the Feishu API is possible.** The supported route:
1. Self-hosted task-management website -> embed it into Feishu as a **网页应用**, add OAuth SSO with `App ID`/`App Secret`, and call `task-v2` APIs from your server with `user_access_token` (after the user logs in) or `tenant_access_token`.

Checklist: Feishu enterprise tenant -> create custom app -> copy `App ID`/`App Secret` -> enable web-app capability and set redirect/home URLs -> request `task:*` (and any `im:*`/`bitable:*`/`drive:*`) scopes -> keep tokens backend-only with refresh -> publish version and get admin review.

## 6. Key references
- Credentials and tokens: https://open.feishu.cn/document/ukTMukTMukTM/uMTNz4yM1MjLzUzM
- Custom app dev flow: https://open.feishu.cn/document/home/introduction-to-custom-app-development/self-built-application-development-process
- Embed existing web app: https://open.feishu.cn/document/uAjLw4CM/uMzNwEjLzcDMx4yM3ATM/embed-web-app-into-feishu-workbench/introduction
- Web-app OAuth login: https://open.feishu.cn/document/common-capabilities/sso/web-application-sso/web-app-overview
- Task create API: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/task-v2/task/create
- Task overview & authorization: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/task-v2/task/overview
- Task list API: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/task-v2/task/list
- Group chat APIs: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat/list
- Bitable record search: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/bitable-v1/app-table-record/search
- Drive file list: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/file/list

## 7. Tasks (任务) - what you can access after login

After OAuth login you hold a `user_access_token` (user identity). You can reach whatever that user can reach, limited by the API scopes the app requested and the admin granted. Verified against task-v2 / im-v1 / bitable-v1 / drive-v1 docs:

**Tasks (`/open-apis/task/v2/...`)**
- CRUD on tasks: `POST/GET/PATCH /open-apis/task/v2/tasks`, `GET /tasks/:task_guid`, plus subtasks (`/task-subtask`), comments, attachments, custom fields, tasklists/sections, reminders, members, dependencies.
- `GET /open-apis/task/v2/tasks` (list) returns the tasks where the caller is "我负责的" (responsible/assignee) - sorted like the task app.
- Access rule (docs): a caller can READ a task if it is the creator, assignee or follower; if the task was shared to them through a group message; if it is a doc task and they are a doc collaborator; if it belongs to a list they collaborate on; or if it is a subtask of a chain they can read. EDIT is limited to creator/assignee, editable doc collaborator, or editable list member/owner.
- Required permission: `task:task:write` / `task:task:writeonly` (write), `task:task:readonly` (read).

**Group chats (`/open-apis/im/v1/...`)**
- `GET /chats` lists the groups the token owner (user or bot) is in; `GET /chats/:chat_id`, `GET /chats/:chat_id/members`, `GET /messages` (history), announcements, tabs, moderation, top notices.
- Prerequisites: bot capability on (for app identity), scopes such as `im:chat:readonly`, `im:message:readonly`; user-identity message reads need extra scopes (`im:message.p2p_msg:get_as_user`, `im:message.group_msg:get_as_user`); for group messages the bot must be in the group (app identity).

**Bitable / tabular (`/open-apis/bitable/v1/...`)**
- Bases, tables, fields, records (list/search/batch create/update/delete), forms, dashboards, roles/advanced permissions: `/apps/:app_token`, `/apps/:app_token/tables`, `/apps/:app_token/tables/:table_id/records/search`.
- Scopes: `bitable:app` / `bitable:app:readonly`, `base:table:read`, `base:record:retrieve`.
- Access depends on who owns the base: user token uses the logged-in user's own base permissions; tenant token (app) only works on bases shared with the app (add the app/bot as a collaborator or via app data scope).

**Data / cloud docs (`/open-apis/drive/v1/...`, docx, sheets, wiki)**
- `GET /open-apis/drive/v1/files` lists accessible files/folders (folder token), then docx/sheet/wiki APIs read/edit content.
- Scopes: `drive:drive` / `drive:drive:readonly`, `space:document:retrieve`, `docx:*`, `sheets:*`, `wiki:*`.

**Answer**: Yes - after the user logs in, the app can access the user's tasks, the group chats they are in, and the Bitable/documents they can open - **but only** the resources covered by (a) the API scopes approved for the app and (b) the user's own permissions. Nothing is accessible by default; every domain needs its scope granted, and user-identity message reading needs the extra "as user" scopes.

## 8. What the API key alone can access (tenant token, no user login)

`App ID + App Secret -> tenant_access_token` acts as the **application identity**, so it can only reach data the app is allowed to see:
- Contact directory: users/departments according to granted contact scopes and the admin-configured data scope (e.g. `contact:user.base:readonly`, `contact:contact:readonly`).
- Tasks: only tasks where the app identity is creator/assignee/follower etc.
- Group chats/messages: only groups where the bot is a member (bot capability + `im:*` scopes).
- Bitable/docs/sheets: only bases/files the app has been added to as collaborator, or that fall inside the app's data-permission scope.
- No "read everything in the tenant": without per-app permission + data scope configuration (and admin approval), most calls return permission errors.
