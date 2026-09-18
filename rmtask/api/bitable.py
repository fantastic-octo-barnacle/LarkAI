"""bitable-v1 wrappers: tables and record search for a known base (app_token)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .base import FeishuClient

TABLES_PATH = "/open-apis/bitable/v1/apps/{app_token}/tables"
FIELDS_PATH = "/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
SEARCH_PATH = "/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
RECORDS_PATH = "/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("value") or json.dumps(value, ensure_ascii=False))
    if isinstance(value, list):
        return " ".join(_value_to_text(v) for v in value)[:500]
    return str(value)


def _value_to_ts(value: Any) -> str:
    """Best-effort ISO extraction from a Bitable date cell (ms number or string)."""
    if isinstance(value, dict):
        value = value.get("timestamp") or value.get("value") or value.get("text")
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        ts = int(text)
        if ts > 10**15:  # microseconds
            ts //= 1000
        if ts > 10**12:  # milliseconds -> seconds
            ts //= 1000
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            return ""
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        return ""


def list_tables(client: FeishuClient, app_token: str, *, token: str | None = None) -> list[dict[str, Any]]:
    return client.list_all(TABLES_PATH.format(app_token=app_token), list_key="items", token=token)


def list_fields(client: FeishuClient, app_token: str, table_id: str, *, token: str | None = None) -> list[dict[str, Any]]:
    return client.list_all(
        FIELDS_PATH.format(app_token=app_token, table_id=table_id),
        list_key="items",
        token=token,
    )


def search_records(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    *,
    page_size: int = 100,
    token: str | None = None,
) -> list[dict[str, Any]]:
    path = SEARCH_PATH.format(app_token=app_token, table_id=table_id)
    items: list[dict[str, Any]] = []
    page_token = ""
    while True:
        data = client.post(path, params={"page_size": page_size, "page_token": page_token}, json={}, token=token)
        items.extend(data.get("items") or [])
        page_token = data.get("page_token") or ""
        if not data.get("has_more") or not page_token:
            break
    return items


def create_record(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    fields: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Create a Bitable record (POST /records with `fields`)."""
    path = RECORDS_PATH.format(app_token=app_token, table_id=table_id)
    data = client.post(path, json={"fields": fields}, token=token)
    return data.get("record") or data


def update_record(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    record_id: str,
    fields: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Update a Bitable record (PUT /records/:record_id with `fields`)."""
    path = f"{RECORDS_PATH.format(app_token=app_token, table_id=table_id)}/{record_id}"
    data = client.put(path, json={"fields": fields}, token=token)
    return data.get("record") or data


def delete_record(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    record_id: str,
    *,
    token: str | None = None,
) -> None:
    """Delete a Bitable record (DELETE /records/:record_id)."""
    path = f"{RECORDS_PATH.format(app_token=app_token, table_id=table_id)}/{record_id}"
    client.delete(path, token=token)


def record_to_fields(record: dict[str, Any]) -> dict[str, str]:
    """Flatten a Bitable record's `fields` into plain strings (record_id preserved)."""
    fields = record.get("fields") or {}
    out = {"record_id": record.get("record_id") or ""}
    for key, value in fields.items():
        out[key] = _value_to_text(value)
    return out


TITLE_HINTS = ("title", "task", "summary", "name", "标题", "任务", "名称", "内容")
TITLE_PREFERENCE = ("名称", "name", "title", "summary", "标题", "任务")
DUE_HINTS = ("due", "deadline", "ddl", "截止", "日期", "date", "时间")
PRIORITY_HINTS = ("priority", "优先级", "优先")
STATUS_HINTS = ("status", "状态")
OWNER_HINTS = ("负责人", "owner", "assignee", "成员")
STATUS_MAP = {
    "待执行": "pending",
    "执行中": "in_progress",
    "已完成": "completed",
    "已取消": "cancelled",
    "取消": "cancelled",
    "终止": "cancelled",
    "暂停": "paused",
}
PRIORITY_MAP = {
    "高": "HIGH",
    "中": "MEDIUM",
    "低": "LOW",
    "紧急": "URGENT",
    "特急": "URGENT",
    "高优先级": "HIGH",
}


def _pick_title(fields: dict[str, Any]) -> str:
    """Pick the most title-like field (prefers 名称/name over ids)."""
    best = ""
    best_score = -1
    for key, value in fields.items():
        key_low = key.lower()
        score = 0
        for i, hint in enumerate(TITLE_PREFERENCE):
            if hint in key_low:
                score = len(TITLE_PREFERENCE) - i
                break
        if score > best_score:
            best_score = score
            best = _value_to_text(value)
    return best


def record_to_event(table_name: str, record: dict[str, Any]) -> dict[str, Any]:
    """Pick title/due from a record with heuristic field-name matching."""
    fields = record.get("fields") or {}
    title = _pick_title(fields)
    due = ""
    priority = ""
    status = ""
    for key, value in fields.items():
        key_low = key.lower()
        if not due and any(h in key_low for h in DUE_HINTS):
            due = _value_to_ts(value)
        if not priority and any(h in key_low for h in PRIORITY_HINTS):
            priority = _value_to_text(value)
        if not status and any(h in key_low for h in STATUS_HINTS):
            status = _value_to_text(value)
    if not title:
        title = _value_to_text(next(iter(fields.values()), "")) if fields else ""
    if not title:
        title = record.get("record_id") or table_name
    description = ""
    for key, value in fields.items():
        key_low = key.lower()
        if any(h in key_low for h in ("备注", "说明", "需求", "description", "comment", "note", "desc")):
            text = _value_to_text(value)
            if text:
                description = text
                break
    if not description:
        summary = [
            f"{k}: {v}"
            for k, v in record_to_fields(record).items()
            if v and k != "record_id" and not any(b in k.lower() for b in ("父记录", "record_id", "任务ID"))
        ]
        description = " | ".join(summary)[:400]
    return {
        "record_id": record.get("record_id") or "",
        "table_name": table_name,
        "title": title,
        "due_iso": due,
        "priority": priority,
        "status": status,
        "description": description,
        "raw": record,
    }


def record_to_task(record: dict[str, Any], table_name: str = "") -> dict[str, Any]:
    """Map a Bitable record to stable task fields (for the local task board)."""
    fields = record.get("fields") or {}
    task_signals = DUE_HINTS + STATUS_HINTS + PRIORITY_HINTS + OWNER_HINTS
    if not any(any(h in key.lower() for h in task_signals) for key in fields):
        # Parent/grouping rows (e.g. only 任务ID + 兵种类型) are not tasks.
        return {}
    ev = record_to_event(table_name, record)
    owner_ids: list[str] = []
    owner_names: list[str] = []
    for key, value in fields.items():
        if not any(h in key.lower() for h in OWNER_HINTS):
            continue
        for item in (value if isinstance(value, list) else [value]):
            if isinstance(item, dict):
                if item.get("id"):
                    owner_ids.append(str(item["id"]))
                name = item.get("name") or item.get("en_name") or ""
                if name:
                    owner_names.append(str(name))
            elif item:
                owner_names.append(str(item))
    return {
        "guid": record.get("record_id") or ev["record_id"] or "",
        "title": ev["title"],
        "description": ev["description"],
        "due_iso": ev["due_iso"],
        "priority": PRIORITY_MAP.get(ev["priority"], "NORMAL"),
        "status": STATUS_MAP.get(ev["status"], "pending"),
        "owner_open_ids": owner_ids,
        "owner_names": owner_names,
        "table_name": table_name or ev["table_name"],
    }
