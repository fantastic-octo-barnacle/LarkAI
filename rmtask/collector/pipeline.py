"""Turn Feishu data into persisted tasks + timeline events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from rmtask.api import bitable as bitable_api
from rmtask.collector.summarizer import build_digest
from rmtask.collector.team import derive_team_info
from rmtask.providers import BaseProvider, now_iso
from rmtask.storage.db import DB
from rmtask.storage.models import EventRecord, TaskRecord


@dataclass
class CollectResult:
    tasks: list[TaskRecord]
    events: list[EventRecord]
    digest: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def task_to_events(tasks: list[TaskRecord]) -> list[EventRecord]:
    events: list[EventRecord] = []
    for t in tasks:
        ts = t.due or t.updated_at or t.created_at
        if not ts:
            continue
        importance = 2
        if t.priority in {"HIGH", "URGENT"}:
            importance = 3
        if t.status == "completed":
            importance = 1
        events.append(EventRecord(
            source="task",
            source_id=t.guid,
            title=f"Task: {t.title}",
            description=t.description,
            ts=ts,
            author=t.creator or t.owner_open_id,
            url=t.url,
            importance=importance,
            tags=["task", t.status, t.priority],
            raw=t.to_dict(),
        ))
    return events


def bitable_events_to_tasks(events: list[EventRecord]) -> list[TaskRecord]:
    """Mirror Bitable records into the local task board (read-only copy)."""
    tasks: list[TaskRecord] = []
    now = now_iso()
    for ev in events:
        table_name = ev.tags[1] if len(ev.tags) > 1 else ""
        info = bitable_api.record_to_task(ev.raw or {}, table_name=table_name)
        if not info or not info.get("guid") or not info.get("title"):
            continue
        tasks.append(TaskRecord(
            guid=info["guid"],
            title=info["title"],
            description=info["description"],
            due=info["due_iso"],
            priority=info["priority"],
            status=info["status"],
            owner_open_id=info["owner_open_ids"][0] if info["owner_open_ids"] else "",
            owner_name=" ".join(info["owner_names"])[:200],
            creator="",
            url="",
            created_at=now,
            updated_at=now,
            source="bitable",
        ))
    return tasks


def collect_all(db: DB, provider: BaseProvider, open_id: str = "") -> CollectResult:
    warnings: list[str] = []
    tasks: list[TaskRecord] = []
    try:
        tasks = provider.list_tasks(open_id)
    except Exception as exc:  # noqa: BLE001 - one failing source must not block the rest
        warnings.append(f"tasks: {exc}")
    for task in tasks:
        db.upsert_task(task)

    events: list[EventRecord] = task_to_events(tasks)
    bitable_events: list[EventRecord] = []
    bitable_ok = False
    source_ok = {"group_chat": False, "calendar": False, "bitable": False}
    for source, fn in (
        ("group_chat", provider.collect_messages),
        ("calendar", provider.collect_meetings),
        ("bitable", provider.collect_bitable),
    ):
        try:
            batch = fn(open_id)
            events.extend(batch)
            source_ok[source] = True
            if source == "bitable":
                bitable_events = batch
                bitable_ok = True
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{source}: {exc}")

    bitable_tasks = bitable_events_to_tasks(bitable_events)
    tasks.extend(bitable_tasks)
    for task in bitable_tasks:
        db.upsert_task(task)

    mode = getattr(getattr(provider, "settings", None), "mode", "mock")
    if mode == "live":
        db.purge_tasks("mock")
        if bitable_ok:
            db.prune_source("bitable", {t.guid for t in bitable_tasks})

    for event in events:
        db.upsert_event(event)

    team = derive_team_info(tasks, events)
    if team.get("facts"):
        if not source_ok["group_chat"]:
            prev_raw = db.get_setting("team_live", "")
            if prev_raw:
                try:
                    prev = json.loads(prev_raw)
                    if prev.get("facts", {}).get("Groups"):
                        team["groups"] = prev.get("groups", team.get("groups", []))
                        team["facts"]["Groups"] = prev["facts"]["Groups"]
                except (ValueError, TypeError):
                    pass
        db.set_setting("team_live", json.dumps(team, ensure_ascii=False))
    db.set_setting("last_sync_ts", now_iso())
    db.set_setting("last_sync_warnings", json.dumps(warnings, ensure_ascii=False))

    digest = build_digest(events, tasks)
    return CollectResult(tasks=tasks, events=events, digest=digest, warnings=warnings)
