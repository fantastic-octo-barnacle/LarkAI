"""Derive live team facts (groups, members, divisions) from collected Feishu data."""

from __future__ import annotations

import re
from typing import Any

from rmtask.storage.models import EventRecord, TaskRecord

DIVISION_RE = re.compile(r"研发组别:\s*([^|]+)")


def derive_team_info(tasks: list[TaskRecord], events: list[EventRecord]) -> dict[str, Any]:
    groups: list[str] = []
    seen: set[str] = set()
    for ev in events:
        if ev.source != "message" or len(ev.tags) < 2:
            continue
        name = ev.tags[1]
        if name and name not in seen:
            seen.add(name)
            groups.append(name)

    members: dict[str, set[str]] = {}
    divisions: set[str] = set()
    for task in tasks:
        if task.source != "bitable":
            continue
        match = DIVISION_RE.search(task.description)
        division = match.group(1).strip() if match else ""
        for part in re.split(r"[\s、,，/]+", division):
            if part.strip():
                divisions.add(part.strip())
        for name in re.split(r"\s+", task.owner_name or ""):
            name = name.strip()
            if not name or name in divisions or name == "用户802654":
                continue
            bucket = members.setdefault(name, set())
            if division:
                bucket.add(division)

    member_rows = sorted(
        (
            {"name": name, "role": "、".join(sorted(value)) if value else "Bitable owner"}
            for name, value in members.items()
        ),
        key=lambda row: row["name"],
    )
    facts = {
        "Groups": str(len(groups)),
        "Members": str(len(member_rows)),
        "Divisions": "、".join(sorted(divisions)) if divisions else "-",
    }
    return {"groups": groups, "members": member_rows, "facts": facts}
