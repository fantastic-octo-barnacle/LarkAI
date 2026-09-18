"""im-v1 wrappers: group chat list and message history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .base import FeishuClient

CHATS_PATH = "/open-apis/im/v1/chats"
MESSAGES_PATH = "/open-apis/im/v1/messages"


def _ms_to_iso(ms: Any) -> str:
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(ms)


def list_chats(client: FeishuClient, *, token: str | None = None) -> list[dict[str, Any]]:
    return client.list_all(CHATS_PATH, list_key="items", token=token, params={"user_id_type": "open_id"})


def list_chat_members(
    client: FeishuClient,
    chat_id: str,
    *,
    page_size: int = 50,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """List group members (open_id + name); externals/guests are included."""
    params: dict[str, Any] = {
        "member_id_type": "open_id",
        "page_size": page_size,
    }
    return client.list_all(f"{CHATS_PATH}/{chat_id}/members", list_key="items", token=token, params=params)


def message_text(item: dict[str, Any]) -> str:
    body = item.get("body") or {}
    content = body.get("content") or ""
    msg_type = item.get("msg_type") or item.get("message_type")
    if msg_type == "text":
        try:
            return json.loads(content).get("text", content)
        except (ValueError, TypeError):
            return content
    return content[:500] or f"[{msg_type or 'message'}]"


def list_messages(
    client: FeishuClient,
    chat_id: str,
    *,
    page_size: int = 50,
    start_iso: str = "",
    end_iso: str = "",
    token: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "container_id_type": "chat",
        "container_id": chat_id,
        "sort_type": "ByCreateTimeAsc",
        "page_size": page_size,
        "user_id_type": "open_id",
    }
    if start_iso:
        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        params["start_time"] = str(int(dt.timestamp()))
    if end_iso:
        dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        params["end_time"] = str(int(dt.timestamp()))
    items = client.list_all(MESSAGES_PATH, list_key="items", token=token, params=params)
    out = []
    for item in items:
        sender = item.get("sender") or {}
        out.append(
            {
                "message_id": item.get("message_id") or "",
                "chat_id": chat_id,
                "ts_iso": _ms_to_iso(item.get("create_time")),
                "sender_id": sender.get("id", ""),
                "sender_type": sender.get("sender_type", ""),
                "message_type": item.get("msg_type") or item.get("message_type", ""),
                "text": message_text(item),
                "raw": item,
            }
        )
    return out
