"""Dataclasses used across providers, collector and web layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskRecord:
    guid: str
    title: str
    description: str = ""
    due: str = ""
    priority: str = "NORMAL"
    status: str = "pending"  # pending | completed | cancelled
    owner_open_id: str = ""
    owner_name: str = ""
    creator: str = ""
    url: str = ""
    created_at: str = ""
    updated_at: str = ""
    source: str = "feishu"

    def to_dict(self) -> dict[str, Any]:
        return {
            "guid": self.guid,
            "title": self.title,
            "description": self.description,
            "due": self.due,
            "priority": self.priority,
            "status": self.status,
            "owner_open_id": self.owner_open_id,
            "owner_name": self.owner_name,
            "creator": self.creator,
            "url": self.url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source": self.source,
        }


@dataclass
class EventRecord:
    source: str  # task | message | meeting | doc
    source_id: str
    title: str
    description: str = ""
    ts: str = ""  # ISO8601 UTC
    author: str = ""
    url: str = ""
    importance: int = 0
    tags: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class UserRecord:
    open_id: str
    name: str = ""
    email: str = ""
    avatar_url: str = ""
    is_admin: bool = False


@dataclass
class TokenRecord:
    open_id: str
    access_token: str
    refresh_token: str = ""
    expires_at: int = 0
    refresh_expires_at: int = 0
    scope: str = ""
