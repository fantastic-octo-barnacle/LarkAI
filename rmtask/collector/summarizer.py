"""Timeline ordering, importance-aware digest and task statistics."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from rmtask.storage.models import EventRecord, TaskRecord


_DIVISION_RE = re.compile(r"研发组别:\s*([^|]+)")
_DIVISION_WORDS = {"机械", "电控", "硬件", "算法", "管理"}
_PLACEHOLDER_USER = re.compile(r"^用户\d+$")


def member_names(owner_name: str) -> list[str]:
    """Split a Bitable owner field into member names (drop placeholders and
    a leading division prefix like ``电控``)."""
    if not owner_name:
        return []
    tokens = [t for t in re.split(r"\s+", owner_name.strip()) if t]
    if tokens and tokens[0] in _DIVISION_WORDS:
        tokens = tokens[1:]
    return [t for t in tokens if not _PLACEHOLDER_USER.match(t)]


def _parse(ts: str) -> datetime:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def timeline_rows(events: list[EventRecord]) -> list[dict[str, Any]]:
    rows = []
    for ev in events:
        rows.append({
            "source": ev.source,
            "source_id": ev.source_id,
            "title": ev.title,
            "description": ev.description,
            "ts": ev.ts,
            "author": ev.author,
            "url": ev.url,
            "importance": ev.importance,
            "tags": ev.tags,
        })
    rows.sort(key=lambda r: (not r["ts"], r["ts"]))
    return rows


def group_by_day(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chronological buckets (ascending) for the time-axis view."""
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row["ts"]:
            continue
        day = _parse(row["ts"]).astimezone().strftime("%Y-%m-%d")
        if not out or out[-1]["day"] != day:
            out.append({"day": day, "items": []})
        out[-1]["items"].append(row)
    return out


def group_by_source(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapsible buckets by event source."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for row in rows:
        if row["source"] not in buckets:
            buckets[row["source"]] = []
            order.append(row["source"])
        buckets[row["source"]].append(row)
    return [{"source": source, "items": buckets[source]} for source in order]


def compute_stats(tasks: list[TaskRecord]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    total = len(tasks)
    pending = [t for t in tasks if t.status == "pending"]
    active = [t for t in tasks if t.status in ("pending", "in_progress")]
    overdue = [t for t in active if t.due and _parse(t.due) < now]
    next_due = sorted(
        (t for t in active if t.due and _parse(t.due) >= now),
        key=lambda t: _parse(t.due),
    )[:5]
    return {
        "total": total,
        "pending": len(pending),
        "in_progress": sum(1 for t in tasks if t.status == "in_progress"),
        "completed": sum(1 for t in tasks if t.status == "completed"),
        "cancelled": sum(1 for t in tasks if t.status == "cancelled"),
        "overdue": len(overdue),
        "next_deadlines": [t.to_dict() for t in next_due],
    }


def compute_workload(tasks: list[TaskRecord]) -> dict[str, Any]:
    """Per-individual workload derived from the task board (live Bitable mirror)."""
    now = datetime.now(timezone.utc)
    members: dict[str, dict[str, Any]] = {}
    for t in tasks:
        names = member_names(t.owner_name)
        if not names:
            continue
        active = t.status in ("pending", "in_progress")
        overdue = active and bool(t.due) and _parse(t.due) < now
        urgent = t.priority in ("URGENT", "HIGH")
        due_dt = _parse(t.due) if t.due else None
        division = ""
        match = _DIVISION_RE.search(t.description or "")
        if match:
            division = match.group(1).strip()
        for name in names:
            m = members.setdefault(name, {
                "name": name, "total": 0, "active": 0, "pending": 0,
                "in_progress": 0, "completed": 0, "cancelled": 0,
                "urgent": 0, "overdue": 0, "divisions": set(),
                "next_due": "", "tasks": [],
            })
            m["total"] += 1
            if active:
                m["active"] += 1
            if t.status == "pending":
                m["pending"] += 1
            elif t.status == "in_progress":
                m["in_progress"] += 1
            elif t.status == "completed":
                m["completed"] += 1
            elif t.status == "cancelled":
                m["cancelled"] += 1
            if urgent:
                m["urgent"] += 1
            if overdue:
                m["overdue"] += 1
            if division:
                m["divisions"].add(division)
            if active and due_dt and (not m["next_due"] or due_dt < _parse(m["next_due"])):
                m["next_due"] = t.due
            m["tasks"].append({
                "guid": t.guid, "title": t.title, "status": t.status,
                "priority": t.priority, "due": t.due, "url": t.url,
            })
    rows = []
    for m in members.values():
        m["divisions"] = sorted(m["divisions"])
        m["tasks"].sort(key=lambda x: (
            x["status"] not in ("pending", "in_progress"),
            _parse(x["due"]) if x["due"] else _parse(""),
        ))
        rows.append(m)
    rows.sort(key=lambda m: (-m["active"], -m["total"], m["name"]))
    return {
        "members": rows,
        "stats": {
            "members": len(rows),
            "active": sum(m["active"] for m in rows),
            "completed": sum(m["completed"] for m in rows),
            "overdue": sum(m["overdue"] for m in rows),
            "urgent": sum(m["urgent"] for m in rows),
            "unassigned": sum(1 for t in tasks if not member_names(t.owner_name)),
        },
    }


def build_digest(events: list[EventRecord], tasks: list[TaskRecord]) -> dict[str, Any]:
    stats = compute_stats(tasks)
    important = [e for e in events if e.importance >= 2]
    important.sort(key=lambda e: (e.importance, e.ts or ""), reverse=True)
    now = datetime.now(timezone.utc)
    upcoming = sorted(
        (e for e in events if e.ts and _parse(e.ts) >= now),
        key=lambda e: _parse(e.ts),
    )[:6]
    rows = timeline_rows(events)
    return {
        "stats": stats,
        "latest_important": [
            {"title": e.title, "ts": e.ts, "source": e.source, "importance": e.importance,
             "url": e.url, "description": e.description[:160]}
            for e in important[:10]
        ],
        "upcoming": [
            {"title": e.title, "ts": e.ts, "source": e.source, "url": e.url}
            for e in upcoming
        ],
        "recent": rows[:8],
    }
