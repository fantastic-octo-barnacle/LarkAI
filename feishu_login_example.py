"""Feishu (Lark) OAuth 2.0 web-app login example (current v3 flow).

Prerequisites:
    1. Create an app at https://open.feishu.cn/app (custom app).
    2. Enable the web-app capability and add FEISHU_REDIRECT_URI to
       开发配置 -> 安全设置 -> 重定向 URL.
    3. Request the scopes you use (task:task:read, etc.) in 权限管理 and
       publish an app version approved by the enterprise admin.

Run:
    pip install flask requests
    cp .env.example .env   # fill in your App ID / App Secret
    python feishu_login_example.py
Then open http://127.0.0.1:5000/oauth/login
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, request, session, url_for

# --------------------------------------------------------------------------
# Minimal .env loader (no extra dependency; python-dotenv also works)
# --------------------------------------------------------------------------


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_dotenv()

# --------------------------------------------------------------------------
# Configuration (from .env or environment variables)
# --------------------------------------------------------------------------

APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
REDIRECT_URI = os.environ.get("FEISHU_REDIRECT_URI", "")
SCOPES = os.environ.get(
    "FEISHU_SCOPES", "auth:user.id:read task:task:read offline_access"
)

# Feishu endpoints (verified against the current docs)
AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
TOKEN_URL = "https://accounts.feishu.cn/oauth/v3/token"
USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
TENANT_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def get_tenant_access_token() -> str:
    """App-identity token (API key only, no user login). Cached with expiry."""
    cached = getattr(get_tenant_access_token, "_cache", None)
    if cached and cached["expires_at"] > datetime.now(timezone.utc):
        return cached["token"]
    resp = requests.post(
        TENANT_TOKEN_URL,
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=15,
    ).json()
    if resp.get("code") != 0:
        raise RuntimeError(f"tenant_access_token failed: {resp}")
    token = resp["tenant_access_token"]
    expires_in = int(resp.get("expire", 7200))
    get_tenant_access_token._cache = {
        "token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60),
    }
    return token


def _push_url(path: str, *, token: str, params: dict | None = None) -> dict:
    url = f"https://open.feishu.cn{path}"
    resp = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    ).json()
    if resp.get("code") != 0:
        raise RuntimeError(f"{path} failed: {resp}")
    return resp.get("data", resp)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{title}</title></head><body><h1>{title}</h1>{body}</body></html>"""


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@app.get("/")
def index():
    return _page(
        "Feishu Login Example",
        f'<p><a href="{url_for("login")}">Login with Feishu</a></p>'
        f"<p>Scopes: <code>{SCOPES}</code></p>",
    )


@app.get("/oauth/login")
def login():
    """Step 1: send the user to the Feishu authorization page."""
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    authorize_url = (
        f"{AUTHORIZE_URL}?"
        + urlencode(
            {
                "client_id": APP_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPES,
                "state": state,
            }
        )
    )
    return redirect(authorize_url)


@app.get("/oauth/callback")
def callback():
    """Step 2: exchange the code for user_access_token."""
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    if session.get("oauth_state") != state:
        return "state mismatch", 400
    if not code:
        return "authorization failed: no code", 400

    token_resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    ).json()
    if token_resp.get("code") != 0 or "access_token" not in token_resp:
        return f"token exchange failed: {token_resp}", 400

    session["user_access_token"] = token_resp["access_token"]
    session["expires_in"] = token_resp.get("expires_in")
    session["refresh_token"] = token_resp.get("refresh_token")
    return redirect(url_for("me"))


@app.get("/me")
def me():
    """Step 3: read the logged-in user's identity."""
    token = session.get("user_access_token")
    if not token:
        return redirect(url_for("login"))
    resp = requests.get(
        USER_INFO_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    ).json()
    return _page(
        "User Info",
        f"<pre>{__import__('json').dumps(resp, indent=2, ensure_ascii=False)}</pre>"
        f'<p><a href="{url_for("tasks")}">List my tasks</a> | '
        f'<a href="{url_for("refresh")}">Refresh token</a></p>',
    )


@app.get("/tasks")
def tasks():
    """Example user-identity API call: GET /open-apis/task/v2/tasks.
    Requires the task:task:read scope and returns the user's assigned tasks."""
    token = session.get("user_access_token")
    if not token:
        return redirect(url_for("login"))
    try:
        data = _push_url("/open-apis/task/v2/tasks", token=token)
    except RuntimeError as exc:
        return str(exc), 400
    return _page(
        "My Tasks",
        f"<pre>{__import__('json').dumps(data, indent=2, ensure_ascii=False)}</pre>",
    )


@app.get("/refresh")
def refresh():
    """Optional: refresh user_access_token with a one-time refresh_token."""
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        return "no refresh_token (grant offline_access and re-login)", 400
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "refresh_token": refresh_token,
        },
        timeout=15,
    ).json()
    if resp.get("code") != 0 or "access_token" not in resp:
        return f"refresh failed: {resp}", 400
    session["user_access_token"] = resp["access_token"]
    session["refresh_token"] = resp.get("refresh_token")
    return _page(
        "Refreshed",
        f"<pre>{__import__('json').dumps(resp, indent=2, ensure_ascii=False)}</pre>"
        f'<p><a href="{url_for("me")}">Back to /me</a></p>',
    )


if __name__ == "__main__":
    if not APP_ID or not APP_SECRET or not REDIRECT_URI:
        raise SystemExit(
            "Set FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_REDIRECT_URI (see .env.example)"
        )
    # Debug only; use a real WSGI server (gunicorn/uvicorn) in production.
    app.run(host="127.0.0.1", port=5000, debug=True)
