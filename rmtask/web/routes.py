"""Web routes: dashboard, timeline, task management, OAuth, notifications."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for

from rmtask.web.feishu_connection import connection_required, safe_return
from rmtask.api import AuthManager
from rmtask.collector.pipeline import collect_all
from rmtask.collector.members import fetch_all_members
from rmtask.collector.summarizer import (
    build_digest,
    compute_stats,
    compute_workload,
    group_by_day,
    group_by_source,
    member_names,
    timeline_rows,
)
from rmtask.errors import FeishuAPIError, ProviderError
from rmtask.notify import Emailer, notify_task_change
from rmtask.storage.models import TaskRecord, TokenRecord, UserRecord

bp = Blueprint("main", __name__)
TIMELINE_SOURCES = ("task", "message", "meeting", "bitable")
_DIVISION_RE = re.compile(r"研发组别:\s*([^|]+)")


def _task_division(description: str) -> str:
    match = _DIVISION_RE.search(description or "")
    return match.group(1).strip() if match else ""


def _assignees() -> list[dict[str, str]]:
    """Known team members: cached directory users first, mirrored task owners as fallback."""
    seen: dict[str, str] = {}
    for member in g.db.list_users():
        if member.open_id and member.name and member.name != member.open_id:
            seen[member.open_id] = member.name
    for task in g.db.list_tasks(limit=1000):
        if not task.owner_open_id:
            continue
        names = member_names(task.owner_name)
        if not names:
            continue  # placeholder user - cannot map confidently
        seen.setdefault(task.owner_open_id, names[0])
    return [{"open_id": oid, "name": name} for oid, name in sorted(seen.items(), key=lambda kv: kv[1])]


def _current_user() -> UserRecord | None:
    open_id = session.get("open_id")
    if not open_id:
        return None
    return g.db.get_user(open_id)


def _is_admin(user: UserRecord | None) -> bool:
    if current_app.config.get("OIDC_ENABLED"):
        return g.get("identity", {}).get("role") == "admin"
    if not user:
        return False
    if user.is_admin:
        return True
    return user.open_id in g.settings.admin_open_ids


def _digest() -> dict:
    tasks = g.db.list_tasks(limit=500)
    events = g.db.list_events(limit=500)
    return build_digest(events, tasks)


@bp.app_context_processor
def _inject() -> dict:
    user = _current_user()
    db = g.get("db")
    last_sync = db.get_setting("last_sync_ts", "") if db else ""
    return {
        "current_user": user,
        "is_admin": _is_admin(user),
        "settings": g.get("settings"),
        "last_sync": last_sync,
    }


@bp.get("/")
def index():
    team = g.provider.get_team_info()
    live_raw = g.db.get_setting("team_live", "")
    if live_raw:
        try:
            live = json.loads(live_raw)
            team = {
                **team,
                "facts": {**(team.get("facts") or {}), **(live.get("facts") or {})},
                "members": live.get("members") or team.get("members", []),
                "derived": True,
            }
        except (ValueError, TypeError):
            pass
    digest = _digest()
    return render_template("index.html", team=team, digest=digest, mode=g.settings.mode)


@bp.get("/timeline")
def timeline():
    q = request.args.get("q", "")
    group = request.args.get("group", "day")
    show = request.args.get("show", "task,meeting,bitable")
    omit_overdue = request.args.get("omit_overdue", "1") != "0"
    sources = [s.strip() for s in show.split(",") if s.strip()]
    events = g.db.list_events(source="", search=q, limit=1000)
    if sources:
        events = [e for e in events if e.source in sources]
    if omit_overdue:
        now = datetime.now(timezone.utc)

        def _ts_utc(ts: str) -> datetime | None:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return None

        events = [e for e in events if not e.ts or ((t := _ts_utc(e.ts)) and t >= now)]
    rows = timeline_rows(events)
    groups = []
    if group == "day":
        groups = group_by_day(rows)
    elif group == "source":
        groups = group_by_source(rows)
    return render_template(
        "timeline.html", events=rows, groups=groups, group=group,
        q=q, show=sources, all_sources=TIMELINE_SOURCES, omit_overdue=omit_overdue,
    )


@bp.get("/tasks")
def tasks_page():
    status = request.args.get("status", "")
    q = request.args.get("q", "")
    group = request.args.get("group", "status")
    tasks = g.db.list_tasks(status=status, search=q, limit=1000)
    order = ["pending", "in_progress", "completed", "cancelled"]
    task_groups: list[dict] = []
    if group == "division":
        buckets: dict[str, list] = {}
        for task in tasks:
            buckets.setdefault(_task_division(task.description) or "未分组", []).append(task)
        task_groups = [{"label": label, "tasks": items} for label, items in buckets.items()]
    elif group == "source":
        buckets = {}
        for task in tasks:
            buckets.setdefault(task.source or "feishu", []).append(task)
        task_groups = [{"label": label, "tasks": items} for label, items in buckets.items()]
    elif group == "none":
        task_groups = [{"label": "All tasks", "tasks": tasks}]
    else:
        task_groups = [
            {"label": label, "tasks": [t for t in tasks if t.status == label]}
            for label in order
            if any(t.status == label for t in tasks)
        ]
        leftovers = [t for t in tasks if t.status not in order]
        if leftovers:
            task_groups.append({"label": "other", "tasks": leftovers})
    try:
        task_options = g.provider.task_create_options(open_id=session.get("open_id", ""))
    except Exception:  # noqa: BLE001
        task_options = {}
    return render_template(
        "tasks.html", tasks=tasks, task_groups=task_groups, group=group,
        status=status, q=q, assignees=_assignees(), task_options=task_options,
    )


@bp.get("/workload")
def workload_page():
    workload = compute_workload(g.db.list_tasks(limit=1000))
    return render_template("workload.html", workload=workload)


@bp.post("/tasks/new")
def task_create():
    user = _current_user()
    if not user:
        flash("Please login first.", "error")
        return redirect(url_for("main.login"))
    title = request.form.get("title", "").strip()
    if not title:
        flash("Task title is required.", "error")
        return redirect(url_for("main.tasks_page"))
    owner_open_ids = [oid.strip() for oid in request.form.getlist("owner_open_id") if oid.strip()]
    if not owner_open_ids and user:
        owner_open_ids = [user.open_id]
    payload = {
        "title": title,
        "description": request.form.get("description", "").strip(),
        "due": request.form.get("due", "").strip(),
        "priority": request.form.get("priority", "NORMAL").upper(),
        "owner_open_ids": owner_open_ids,
        "owner_open_id": owner_open_ids[0] if owner_open_ids else "",
        "category": request.form.get("category", "").strip(),
        "divisions": [d for d in request.form.getlist("divisions") if d.strip()],
        "remark": request.form.get("remark", "").strip(),
    }
    try:
        task = g.provider.create_task(payload, open_id=user.open_id if user else "")
    except (ProviderError, FeishuAPIError) as exc:
        flash(f"Create failed: {exc}", "error")
        return redirect(url_for("main.tasks_page"))
    g.db.upsert_task(task)
    notify_task_change(g.db, Emailer(g.settings), g.settings, kind="created", task=task,
                       actor=user.name if user else "")
    flash(f"Task '{task.title}' created.", "success")
    return redirect(url_for("main.tasks_page"))


def _update_status(kind: str, guid: str, method: str) -> object:
    user = _current_user()
    if not user:
        flash("Please login first.", "error")
        return redirect(url_for("main.login"))
    try:
        task = getattr(g.provider, method)(guid, open_id=user.open_id)
    except (ProviderError, FeishuAPIError) as exc:
        flash(f"{kind.title()} failed: {exc}", "error")
        return redirect(url_for("main.tasks_page"))
    g.db.upsert_task(task)
    notify_task_change(g.db, Emailer(g.settings), g.settings, kind=kind, task=task, actor=user.name)
    flash(f"Task '{task.title}' {kind}.", "success")
    return redirect(url_for("main.tasks_page"))


@bp.post("/tasks/<guid>/cancel")
def task_cancel(guid: str):
    return _update_status("cancelled", guid, "cancel_task")


@bp.post("/tasks/<guid>/complete")
def task_complete(guid: str):
    return _update_status("completed", guid, "complete_task")


@bp.post("/tasks/<guid>/delete")
def task_delete(guid: str):
    user = _current_user()
    if not _is_admin(user):
        flash("Only admins can delete tasks.", "error")
        return redirect(url_for("main.tasks_page"))
    task = g.db.get_task(guid)
    try:
        g.provider.delete_task(guid, open_id=user.open_id if user else "")
    except (ProviderError, FeishuAPIError) as exc:
        flash(f"Delete failed: {exc}", "error")
        return redirect(url_for("main.tasks_page"))
    if task:
        notify_task_change(g.db, Emailer(g.settings), g.settings, kind="deleted", task=task,
                           actor=user.name if user else "")
    g.db.delete_task(guid)
    flash("Task deleted.", "success")
    return redirect(url_for("main.tasks_page"))


@bp.post("/sync")
def sync():
    user = _current_user()
    if not _is_admin(user):
        flash("Only admins can sync.", "error")
        return redirect(url_for("main.index"))
    result = collect_all(g.db, g.provider, open_id=user.open_id if user else "")
    flash(f"Synced {len(result.tasks)} tasks and {len(result.events)} timeline items.", "success")
    for warning in result.warnings:
        flash(warning, "error")
    return redirect(url_for("main.index"))


@bp.post("/members/refresh")
def members_refresh():
    user = _current_user()
    if not _is_admin(user):
        flash("Only admins can refresh members.", "error")
        return redirect(url_for("main.index"))
    if g.settings.mode != "live":
        flash("Member refresh requires live Feishu mode.", "error")
        return redirect(url_for("main.tasks_page"))
    try:
        result = fetch_all_members(g.provider, g.db, open_id=user.open_id if user else "")
    except (ProviderError, FeishuAPIError) as exc:
        flash(f"Member refresh failed: {exc}", "error")
        return redirect(url_for("main.tasks_page"))
    flash(f"Members updated: {result['users']} total ({result['org']} org, {result['chat_members']} chat).", "success")
    for warning in result["warnings"]:
        flash(warning, "error")
    return redirect(url_for("main.tasks_page"))


@bp.get("/diagnostics")
def diagnostics():
    user = _current_user()
    if not _is_admin(user):
        flash("Only admins can run diagnostics.", "error")
        return redirect(url_for("main.index"))
    rows = g.provider.diagnostics(open_id=user.open_id if user else "")
    return render_template("diagnostics.html", rows=rows)


@bp.get("/notifications")
def notifications():
    rows = g.db.list_notifications()
    return render_template("notifications.html", rows=rows)


@bp.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        if request.form.get("action") == "test":
            notify_task_change(g.db, Emailer(g.settings), g.settings, kind="updated",
                               task=TaskRecord(guid="test", title="Notification test"),
                               actor="system")
            flash("Test notification recorded (check delivery status below).", "success")
        else:
            g.db.set_setting("email_recipients", request.form.get("email_recipients", "").strip().replace(",", " "))
            flash("Settings saved.", "success")
        return redirect(url_for("main.settings_page"))
    return render_template(
        "settings.html",
        email_recipients=g.db.get_setting("email_recipients", " ".join(g.settings.email_to)),
        smtp_configured=g.settings.email_configured,
        smtp_host=g.settings.smtp_host,
    )


@bp.get("/login")
def login():
    session["feishu_return_to"] = safe_return(request.args.get("next"))
    if g.settings.mode == "mock":
        demo = UserRecord(
            open_id="ou_demo_user",
            name="Demo Driver",
            email="demo@example.com",
            is_admin=True,
        )
        g.db.upsert_user(demo)
        session["open_id"] = demo.open_id
        flash("Logged in as demo user (mock mode).", "success")
        return redirect(url_for("main.index"))
    if not g.settings.app_id or not g.settings.app_secret or not g.settings.redirect_uri:
        return connection_required(session["feishu_return_to"], status=503)
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    auth = AuthManager(g.settings)
    return redirect(auth.build_authorize_url(state))


@bp.get("/oauth/callback")
def oauth_callback():
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    expected_state = session.pop("oauth_state", None)
    if not expected_state or not state or not secrets.compare_digest(expected_state, state):
        return "state mismatch", 400
    target = safe_return(session.pop("feishu_return_to", None))
    if not code:
        return connection_required(target, message="Feishu access was not granted. You can try again or return to the dashboard.", status=400)
    auth = AuthManager(g.settings)
    try:
        tokens = auth.exchange_code(code)
        info = auth.user_info(tokens["access_token"])
    except Exception:  # Keep upstream token/error payloads out of browser responses.
        return connection_required(target, message="Feishu connection could not be verified. Please try again.", status=400)
    data = info.get("data", info)
    open_id = data.get("open_id") or data.get("user_id") or ""
    if not open_id:
        return "Feishu did not return an Open ID", 400
    if current_app.config.get("OIDC_ENABLED"):
        try:
            g.db.link_feishu(g.identity["sub"], open_id)
        except sqlite3.IntegrityError:
            return "This Feishu account is already connected to another account", 409
    is_admin = open_id in g.settings.admin_open_ids
    if not current_app.config.get("OIDC_ENABLED") and not g.settings.admin_open_ids and not any(u.is_admin for u in g.db.list_users()):
        is_admin = True  # first user to log in becomes admin until FEISHU_ADMIN_OPEN_IDS is set
    user = UserRecord(
        open_id=open_id,
        name=data.get("name", open_id),
        email=data.get("email", ""),
        avatar_url=data.get("avatar_url", ""),
        is_admin=False if current_app.config.get("OIDC_ENABLED") else is_admin,
    )
    g.db.upsert_user(user)
    now = int(datetime.now(timezone.utc).timestamp())
    g.db.save_token(TokenRecord(
        open_id=open_id,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token", ""),
        expires_at=now + int(tokens.get("expires_in", 7200)),
        refresh_expires_at=now + int(tokens.get("refresh_token_expires_in", 0)),
        scope=tokens.get("scope", ""),
    ))
    session["open_id"] = open_id
    return redirect(target)


@bp.get("/logout")
def logout():
    session.pop("open_id", None)
    return redirect(url_for("main.index"))


# -- JSON APIs used by the frontend -----------------------------------------
@bp.get("/api/stats.json")
def api_stats():
    return jsonify(compute_stats(g.db.list_tasks(limit=500)))


@bp.get("/api/timeline.json")
def api_timeline():
    return jsonify(timeline_rows(g.db.list_events(limit=400)))


@bp.get("/api/team.json")
def api_team():
    return jsonify(g.provider.get_team_info())


@bp.get("/api/members.json")
def api_members():
    return jsonify(_assignees())


@bp.get("/api/workload.json")
def api_workload():
    return jsonify(compute_workload(g.db.list_tasks(limit=1000)))
