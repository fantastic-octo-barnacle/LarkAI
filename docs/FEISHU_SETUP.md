# Feishu setup

1. Create an enterprise custom app at the Feishu Open Platform console and copy the App ID and App Secret into backend environment variables.
2. Enable the web application capability and configure the website URL.
3. Register the exact `FEISHU_REDIRECT_URI`, normally `https://your.domain/oauth/callback`. For local development use port 8000 (Axum hosting) or 5173 (Vite proxy hosting), keeping the same browser hostname.
4. Grant and publish the scopes needed by the app. The `.env.example` scope list covers identity, tasks, chats, messages, calendars, wiki resolution, Bitable and contacts. Add `base:record:update`, `base:record:delete` and `base:field:read` for Bitable actions and form options. Grant contact and email scopes for member email notifications.
5. Publish the app version, obtain the enterprise administrator's approval and ensure your account is in the app's availability range. Reconnect Feishu after changing scopes; a refresh token does not acquire new scopes automatically.

Set `FEISHU_MODE=live` and click **Connect Feishu**. The Rust backend exchanges the code at `https://accounts.feishu.cn/oauth/v3/token`, reads `/open-apis/authen/v1/user_info`, and stores the connection server-side. Refreshes are serialized to avoid concurrent use of rotating refresh tokens. Missing/expired authorization returns a reconnect prompt without blocking shared dashboard access.

With Herkules OIDC enabled, website identity and roles come from Herkules, while Feishu is linked by immutable subject. Without OIDC, `FEISHU_ADMIN_OPEN_IDS` controls administrators; if empty, the first Feishu login becomes admin.

For Bitable, configure either `FEISHU_BITABLE_APP_TOKEN` or `FEISHU_WIKI_NODE_TOKEN`. A wiki token is resolved to the underlying Bitable object token. Set `FEISHU_BITABLE_SUBMIT_TABLE_ID` for task creation. Default field mappings match the RoboMaster base; override the `FEISHU_BITABLE_*_FIELD` values to match your schema. Updates use each mirrored record's source table.

Collection uses the connected user's token and sees only resources that user and the app scopes permit. Group access may additionally require enabling the bot capability and adding it to the relevant chats. The **Diagnostics** page checks API reachability, and sync warnings identify failing sources. Inspect server logs for upstream error codes, grant the missing permissions, publish, and reconnect.

Secrets belong only in the backend environment. They are never sent to React or included in a Vite build.
