"""task-v2 wrappers: list, get, create, update, complete, delete tasks.

Verified against the current official docs (retrieved 2026-09-16):
  * create  - POST   /open-apis/task/v2/tasks
  * list    - GET    /open-apis/task/v2/tasks?type=my_tasks  (data.items)
  * patch   - PATCH  /open-apis/task/v2/tasks/:task_guid  (body: {task, update_fields})
  * delete  - DELETE /open-apis/task/v2/tasks/:task_guid
Note: task-v2 has no `priority` field; priority is a local concept in this repo.
"""

from __future__ import annotations

import uuid
import time
from datetime import datetime, timezone
from typing import Any

from .base import FeishuClient

TASK_PATH = "/open-apis/task/v2/tasks"
_LOCAL_TZ = datetime.now().astimezone().tzinfo


def _ts_to_iso(ts: Any) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(ts)


def _iso_to_ts(iso: str | None) -> dict[str, Any]:
    if not iso:
        return {}
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_LOCAL_TZ)
        return {"timestamp": str(int(dt.timestamp() * 1000)), "is_all_day": False}
    except ValueError:
        return {}


def normalize_task(item: dict[str, Any]) -> dict[str, Any]:
    """Map raw task-v2 item fields to stable local names."""
    due = item.get("due") or {}
    completed_at = item.get("completed_at") or ""
    return {
        "guid": item.get("guid") or "",
        "summary": item.get("summary") or "",
        "description": item.get("description") or "",
        "due_iso": _ts_to_iso(due.get("timestamp")),
        "completed": str(completed_at) not in {"", "0"},
        "creator": (item.get("creator") or {}).get("id", ""),
        "members": item.get("members") or [],
        "url": item.get("url") or "",
        "source": item.get("source") or "",
        "created_at_iso": _ts_to_iso(item.get("created_at")),
        "modified_at_iso": _ts_to_iso(item.get("modified_at") or item.get("updated_at")),
        "raw": item,
    }


def list_tasks(client: FeishuClient, *, token: str | None = None) -> list[dict[str, Any]]:
    items = client.list_all(TASK_PATH, list_key="items", token=token, params={"type": "my_tasks"})
    return [normalize_task(item) for item in items]


def get_task(client: FeishuClient, guid: str, *, token: str | None = None) -> dict[str, Any]:
    data = client.get(f"{TASK_PATH}/{guid}", token=token)
    return normalize_task(data.get("task", data))


def create_task(
    client: FeishuClient,
    *,
    summary: str,
    description: str = "",
    due_iso: str = "",
    assignee_open_id: str = "",
    token: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": summary,
        "client_token": uuid.uuid4().hex,
    }
    if description:
        body["description"] = description
    due = _iso_to_ts(due_iso)
    if due:
        body["due"] = due
    if assignee_open_id:
        body["members"] = [{"id": assignee_open_id, "type": "user", "role": "assignee"}]
    data = client.post(TASK_PATH, json=body, token=token)
    return normalize_task(data.get("task", data))


def update_task(
    client: FeishuClient,
    guid: str,
    fields: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PATCH a task. `fields` may contain summary/description/priority/due_iso/completed."""
    task_body: dict[str, Any] = {}
    update_fields: list[str] = []
    for key in ("summary", "description"):
        if key in fields:
            task_body[key] = fields[key]
            update_fields.append(key)
    if "completed" in fields:
        ts = str(int(time.time() * 1000)) if fields["completed"] else "0"
        task_body["completed_at"] = ts
        update_fields.append("completed_at")
    if "due_iso" in fields:
        due = _iso_to_ts(fields["due_iso"])
        if due:
            task_body["due"] = due
            update_fields.append("due")
    if not update_fields:
        raise ValueError("update_task: no supported fields provided")
    body = {"task": task_body, "update_fields": update_fields}
    data = client.patch(f"{TASK_PATH}/{guid}", json=body, token=token)
    return normalize_task(data.get("task", data))


def complete_task(client: FeishuClient, guid: str, *, token: str | None = None) -> dict[str, Any]:
    return update_task(client, guid, {"completed": True}, token=token)


def delete_task(client: FeishuClient, guid: str, *, token: str | None = None) -> None:
    client.delete(f"{TASK_PATH}/{guid}", token=token)
