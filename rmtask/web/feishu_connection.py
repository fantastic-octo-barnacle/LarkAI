"""On-demand Feishu authorization, separate from the Herkules site session."""
from __future__ import annotations

import time
from urllib.parse import urlsplit

from flask import g, jsonify, render_template, request, session, url_for

# OAuth continuations never accept external URLs, callback URLs or mutation routes.
RETURN_PATHS = {'/', '/tasks', '/timeline', '/workload', '/diagnostics', '/settings', '/notifications'}
FEISHU_ENDPOINTS = {
    'main.tasks_page', 'main.task_create', 'main.task_complete',
    'main.task_cancel', 'main.task_delete', 'main.sync', 'main.diagnostics', 'main.members_refresh',
}


def safe_return(value: str | None, default: str = '/tasks') -> str:
    value = value or default
    if any(ord(c) < 32 for c in value) or '\\' in value:
        return default
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment or parsed.path not in RETURN_PATHS:
        return default
    return value


def connection_required(next_path: str, *, message: str = '', status: int = 403):
    target = safe_return(next_path)
    connect_url = url_for('main.login', next=target)
    if request.is_json or request.path.startswith('/api/'):
        return jsonify(error='feishu_connection_required', connect_url=connect_url), status
    return render_template('connect_feishu.html', connect_url=connect_url, message=message), status


def require_feishu():
    if g.settings.mode != 'live' or request.endpoint not in FEISHU_ENDPOINTS:
        return None
    # Site identity alone never grants permission to act as an arbitrary Feishu user.
    uid = session.get('open_id', '')
    token = g.db.get_token(uid) if uid else None
    available = False
    if token:
        try:
            # Reuse the provider's refresh path, then check the persisted expiry.
            access_token = g.provider._user_token(uid)
            refreshed = g.db.get_token(uid)
            available = bool(access_token and refreshed and refreshed.expires_at > time.time())
        except Exception:  # Provider errors must lead to reconnect, never tenant-token fallback.
            available = False
    if available:
        return None
    target = request.full_path.rstrip('?') if request.method == 'GET' else '/tasks'
    return connection_required(target)
