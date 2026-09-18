"""Timeline ordering, importance-aware digest and task statistics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rmtask.storage.models import EventRecord, TaskRecord


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
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows


def group_by_day(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chronological buckets (descending) for the time-axis view."""
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
