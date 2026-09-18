"""calendar-v4 / meeting wrappers: calendars and events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import FeishuClient

CALENDARS_PATH = "/open-apis/calendar/v4/calendars"


def _ts_to_iso(ts: Any) -> str:
    if not ts:
        return ""
    try:
        value = int(ts)
        if value > 10**12:  # milliseconds -> seconds
            value = value // 1000
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(ts)


def list_calendars(client: FeishuClient, *, token: str | None = None) -> list[dict[str, Any]]:
    return client.list_all(CALENDARS_PATH, list_key="calendar_list", token=token)


def list_events(
    client: FeishuClient,
    calendar_id: str,
    *,
    start_iso: str = "",
    end_iso: str = "",
    token: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if start_iso:
        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        params["start_time"] = str(int(dt.timestamp()))
    if end_iso:
        dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        params["end_time"] = str(int(dt.timestamp()))
    items = client.list_all(f"{CALENDARS_PATH}/{calendar_id}/events", list_key="items", token=token, params=params)
    out = []
    for item in items:
        start = item.get("start_time") or {}
        end = item.get("end_time") or {}
        out.append(
            {
                "event_id": item.get("event_id") or "",
                "calendar_id": calendar_id,
                "summary": item.get("summary") or "",
                "description": item.get("description") or "",
                "start_iso": _ts_to_iso(start.get("timestamp")),
                "end_iso": _ts_to_iso(end.get("timestamp")),
                "url": item.get("url") or "",
                "raw": item,
            }
        )
    return out
