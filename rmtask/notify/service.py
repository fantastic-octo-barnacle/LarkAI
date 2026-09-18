"""Task-change notification service with DB audit trail."""

from __future__ import annotations

import html as html_escape

from rmtask.config import Settings
from rmtask.notify.emailer import Emailer
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
            status = emailer.send(subject, body, text)
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
    _deliver(db, emailer, settings, kind=f"task_{kind}", subject=subject,
             text=text, body=body, recipients=recipients)
