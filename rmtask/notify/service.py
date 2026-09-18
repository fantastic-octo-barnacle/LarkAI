"""Task-change notification service with DB audit trail."""

from __future__ import annotations

import html as html_escape
from datetime import datetime, timezone

from rmtask.collector.pipeline import CollectResult
from rmtask.config import Settings
from rmtask.notify.emailer import Emailer
from rmtask.providers import now_iso
from rmtask.storage.db import DB
from rmtask.storage.models import TaskRecord


def _recipients(db: DB, settings: Settings) -> str:
    override = db.get_setting("email_recipients", "")
    if override:
        return override
    return " ".join(settings.email_to)


def _deliver(db: DB, emailer: Emailer, settings: Settings, *, kind: str,
             subject: str, text: str, body: str, recipients: str) -> None:
    status = "skipped"
    error = ""
    try:
        if settings.notify_on_task_change and recipients:
            status = emailer.send(subject, body, text, recipients=recipients)
    except Exception as exc:  # noqa: BLE001 - audit trail must survive email failures
        status = "failed"
        error = str(exc)[:500]
    db.add_notification(kind=kind, subject=subject[:200], body=text,
                        recipients=recipients, status=status, error=error)


def notify_important_digest(
    db: DB,
    emailer: Emailer,
    settings: Settings,
    *,
    items: list[dict],
) -> None:
    """Email + audit a digest of the latest important timeline items."""
    if not items:
        return
    subject = f"[{settings.tenant_name}] Important updates ({len(items)})"
    rows = [f"- [{i.get('source')}] {i.get('title')} ({i.get('ts', '')[:16]})" for i in items]
    text = "Important updates:\n\n" + "\n".join(rows)
    body = "<h2>Important updates</h2><ul>" + "".join(f"<li>{e}</li>" for e in rows) + "</ul>"
    recipients = _recipients(db, settings)
    _deliver(db, emailer, settings, kind="digest_important", subject=subject,
             text=text, body=body, recipients=recipients)


def notify_task_change(
    db: DB,
    emailer: Emailer,
    settings: Settings,
    *,
    kind: str,
    task: TaskRecord,
    actor: str = "",
) -> None:
    """Record + optionally email a task lifecycle event. Never raises."""
    labels = {
        "created": "New Task",
        "updated": "Task Updated",
        "completed": "Task Completed",
        "cancelled": "Task Cancelled",
        "deleted": "Task Deleted",
    }
    subject = f"[{settings.tenant_name}] {labels.get(kind, kind)}: {task.title}"
    text = (
        f"{labels.get(kind, kind)}\n\n"
        f"Task: {task.title}\nDescription: {task.description}\n"
        f"Priority: {task.priority}\nDue: {task.due or 'not set'}\n"
        f"Status: {task.status}\nActor: {actor or 'system'}\n"
    )
    body = (
        f"<h2>{html_escape.escape(labels.get(kind, kind))}</h2>"
        f"<p><b>Task:</b> {html_escape.escape(task.title)}</p>"
        f"<p><b>Description:</b> {html_escape.escape(task.description or '')}</p>"
        f"<p><b>Priority:</b> {html_escape.escape(task.priority)}</p>"
        f"<p><b>Due:</b> {html_escape.escape(task.due or 'not set')}</p>"
        f"<p><b>Status:</b> {html_escape.escape(task.status)}</p>"
        f"<p><b>Actor:</b> {html_escape.escape(actor or 'system')}</p>"
    )
    recipients = _recipients(db, settings)
    owner = db.get_user(task.owner_open_id) if task.owner_open_id else None
    if owner and owner.email and owner.email not in recipients.split():
        recipients = (recipients + " " + owner.email).strip()
    _deliver(db, emailer, settings, kind=f"task_{kind}", subject=subject,
             text=text, body=body, recipients=recipients)


def _parse_ts(value: str) -> float:
    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


def maybe_send_digest(db: DB, settings: Settings, result: CollectResult) -> None:
    """Email a digest of important items that appeared since the last digest.

    The first run only records a baseline (no email), so an existing store does
    not trigger an immediate digest. Shared by the server auto-collect loop and
    the CLI `scripts/collect.py --notify`. Task-change emails are handled
    separately by the web routes.
    """
    if settings.mode != "live" or not settings.notify_on_task_change:
        return
    if not Emailer(settings).configured:
        return
    now = now_iso()
    last = db.get_setting("last_digest_ts", "")
    items = result.digest.get("latest_important") or []
    if last:
        last_ts = _parse_ts(last)
        fresh = [i for i in items if i.get("ts") and _parse_ts(i["ts"]) > last_ts + 1]
    else:
        fresh = []
    if fresh:
        notify_important_digest(db, Emailer(settings), settings, items=fresh)
    db.set_setting("last_digest_ts", now)
