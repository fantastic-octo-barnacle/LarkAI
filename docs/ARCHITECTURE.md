# Architecture

The browser runs a React/TypeScript SPA built by Vite. In development, Vite proxies `/api`, `/auth`, `/oauth`, `/oidc` and `/healthz` to Axum on port 8000. In production, Axum serves both the JSON API and `frontend/dist`, with an index fallback for client routes. No Flask or Python application process remains.

## Backend

- `config.rs`: environment loading and startup validation.
- `auth.rs`: opaque server-side sessions, CSRF, Herkules OIDC authorization code flow with PKCE/state/nonce, discovery-advertised RS256/ES256/EdDSA signature validation plus issuer/audience checks, optional Cloudflare Access validation, Feishu login/linking.
- `provider.rs`: Feishu OAuth refresh, paginated collection, normalization, task-v2 and Bitable mutations, directory refresh.
- `model.rs`: stable typed domain objects and statistics. Tasks hold a list of owners, divisions, remote ID, source and source table ID.
- `store.rs`: asynchronous SQLx/SQLite persistence and transactional source replacement.
- `notify.rs`: SMTP delivery and notification audit records. Delivery runs asynchronously and failures do not undo a successful task operation.
- `web.rs`: API authorization, validation and routing.

SQLite stores tasks/events/members as typed JSON cache entries, with separate tables for settings, identity connections, sessions and notification history. Namespaced IDs avoid collisions across task-v2, Bitable tables and mock tasks. SQLx applies versioned migrations on startup. `DATABASE_PATH` defaults to a new `data/larkai.sqlite3`; there is no old-data migration.

Feishu connection ownership is unique by open ID and linked to OIDC `sub`, never email. Tokens and SMTP credentials remain server-side. The cookie contains only a random session ID and uses HttpOnly/SameSite=Lax; HTTPS enables Secure and the `__Host-` prefix. Every mutation requires the session CSRF token in `X-CSRF-Token`. Herkules UserInfo establishes the role at sign-in. Protected requests validate the ID token locally using cached JWKS; sessions expire within 15 minutes, when roles and account status are rechecked through sign-in.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/healthz` | Unauthenticated liveness |
| GET | `/api/session` | User, CSRF token, mode, connection state |
| GET | `/api/dashboard` | Stats, deadlines, updates, members, last sync |
| GET / POST | `/api/tasks` | Filter tasks / create task |
| POST | `/api/tasks/{id}/{complete,cancel,delete}` | Mutate a task |
| GET | `/api/task-options` | Bitable categories/divisions or defaults |
| GET | `/api/timeline` | Source/search/date-filtered events |
| GET | `/api/workload` | Per-member tasks and counts |
| GET | `/api/members` | Cached directory |
| POST | `/api/members/refresh` | Refresh directory and group members |
| POST | `/api/sync` | Collect remote data |
| GET | `/api/notifications` | Delivery audit |
| GET / PUT | `/api/settings` | Notification configuration |
| POST | `/api/settings/test` | Send a test notification |
| GET | `/api/diagnostics` | Connection checks |
| POST | `/api/logout` | Invalidate browser session |

Login entry points are `/auth/login` and `/auth/feishu`; callbacks are `/oidc/callback` and `/oauth/callback`. APIs return 401 for missing website identity, 428 for a missing/expired Feishu connection, 403 for role/CSRF rejection and 400 for invalid task fields. JSON APIs never redirect a failed mutation into an OAuth replay.

Shared data pages remain readable without a personal Feishu connection. Task actions require a connection; administrative routes additionally require an admin role. In local deployments without OIDC, shared data pages are public, matching the development workflow. Use OIDC to protect a live deployment.

Collection and task mutations share an in-process lock; refresh tokens have a separate lock. Run one replica per database. A failed collection source retains its last successful data. Bitable/messages/calendar snapshots replace their source atomically only after all pages succeed. Task-v2 collection upserts because each user sees a different `my_tasks` subset; explicit deletes remove local tasks after upstream success.

## Request timing and startup

Every response includes `Server-Timing` (milliseconds) and a generated `X-Request-ID`. The same ID, route template, method, status and timings are logged as `HTTP request completed`; query strings, credentials and request bodies are not logged by this instrumentation. `total` measures server work until response headers are ready, excluding body streaming and client/network latency. `auth` and `handler` are the major phases. `db` measures instrumented database operations including pool waits and decoding; `upstream` measures Feishu requests/token exchange and discovery/JWKS cache misses. These submetrics overlap their parent phases and must not be added to `total`. This is wall-clock request instrumentation, not CPU sampling.

`GET /api/bootstrap?page=/tasks` returns session details and the first page's data in one response. It runs the same handlers and permission checks as the individual APIs; a page error is returned separately from the session. React consumes the initial page result once, then uses normal fresh requests for navigation and mutations. Task form options and members load only when opening the form.

Existing files under Vite's `/assets/` directory use `Cache-Control: private, max-age=31536000, immutable` and do not renew the session cookie. Vite content hashes change asset URLs after edits. Missing assets return 404 rather than the SPA document. HTML, APIs and errors remain `no-store`; shared/CDN caching is not enabled for authenticated responses.
