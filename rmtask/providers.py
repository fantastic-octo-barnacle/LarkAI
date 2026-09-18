"""Provider abstraction: `LiveProvider` (Feishu API) and `MockProvider` (empty offline state)."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rmtask.api import AuthManager, FeishuClient
from rmtask.api import bitable as bitable_api
from rmtask.api import calendar as cal_api
from rmtask.api import im as im_api
from rmtask.api import tasks as task_api
from rmtask.api import wiki as wiki_api
from rmtask.config import ROOT, Settings
from rmtask.errors import AuthError, FeishuAPIError, ProviderError
from rmtask.storage.db import DB
from rmtask.storage.models import EventRecord, TaskRecord, TokenRecord, UserRecord


_LOCAL_TZ = datetime.now().astimezone().tzinfo


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class BaseProvider:
    def get_team_info(self) -> dict[str, Any]:
        return _load_json(ROOT / "data" / "team_info.json", {})

    def task_create_options(self, open_id: str = "") -> dict[str, list[str]]:
        return {}

    # Task operations (all return TaskRecord / None).
    def list_tasks(self, open_id: str = "") -> list[TaskRecord]:
        raise NotImplementedError

    def create_task(self, payload: dict[str, Any], open_id: str = "") -> TaskRecord:
        raise NotImplementedError

    def update_task(self, guid: str, fields: dict[str, Any], open_id: str = "") -> TaskRecord:
        raise NotImplementedError

    def cancel_task(self, guid: str, open_id: str = "") -> TaskRecord:
        raise NotImplementedError

    def complete_task(self, guid: str, open_id: str = "") -> TaskRecord:
        raise NotImplementedError

    def delete_task(self, guid: str, open_id: str = "") -> None:
        raise NotImplementedError

    # Collection (returns normalized events).
    def collect_messages(self, open_id: str = "") -> list[EventRecord]:
        return []

    def collect_meetings(self, open_id: str = "") -> list[EventRecord]:
        return []

    def collect_bitable(self, open_id: str = "") -> list[EventRecord]:
        return []

    def diagnostics(self, open_id: str = "") -> list[dict]:
        """Return [{name, ok, detail}] for the status page."""
        checks: list[dict] = []

        def add(name: str, fn) -> None:
            try:
                detail = fn()
                checks.append({"name": name, "ok": True, "detail": str(detail)[:200]})
            except Exception as exc:  # noqa: BLE001 - report, never crash the page
                checks.append({"name": name, "ok": False, "detail": str(exc)[:300]})

        add("mode", lambda: self.settings.mode)
        return checks


def _record_from_feishu(item: dict[str, Any], local_status: str = "") -> TaskRecord:
    members = item.get("members") or []
    assignee = next((m for m in members if m.get("role") == "assignee"), None)
    owner = assignee.get("id", "") if assignee else (item.get("creator") or "")
    if item.get("completed"):
        status = local_status if local_status == "cancelled" else "completed"
    else:
        status = "pending"
    return TaskRecord(
        guid=item.get("guid", ""),
        title=item.get("summary") or item.get("title") or "(untitled)",
        description=item.get("description") or "",
        due=item.get("due_iso") or "",
        priority=item.get("priority") or "NORMAL",
        status=status,
        owner_open_id=owner,
        owner_name="",
        creator=(item.get("creator") or ""),
        url=item.get("url") or "",
        created_at="",
        updated_at=now_iso(),
        source="feishu",
    )


_PRIORITY_TO_BITABLE = {"URGENT": "高", "HIGH": "高", "MEDIUM": "中", "NORMAL": "中", "LOW": "低"}

DEFAULT_TASK_OPTIONS: dict[str, list[str]] = {
    "types": ["步兵（HKU）", "哨兵（HKU）", "无人机", "飞镖", "总车组", "场地设施",
              "步兵（CUHKSZ）", "重装", "哨兵（CUHKSZ）"],
    "divisions": ["机械", "硬件", "算法", "电控", "管理", "宣营"],
    "priorities": ["高", "中", "低"],
}
_task_options_cache: dict[str, tuple[float, dict[str, list[str]]]] = {}


def _assignee_ids(payload: dict[str, Any], fallback_open_id: str = "") -> list[str]:
    """Normalize single/multi assignee fields into a de-duplicated open_id list."""
    ids = [oid for oid in (payload.get("owner_open_ids") or []) if oid]
    owner = payload.get("owner_open_id") or ""
    if owner and owner not in ids:
        ids.insert(0, owner)
    if not ids and fallback_open_id:
        ids = [fallback_open_id]
    return ids


def _bitable_task_fields(payload: dict[str, Any], settings: Settings, owner_open_id: str = "") -> dict[str, Any]:
    """Map a website task payload onto the Bitable column names (configurable)."""
    fields: dict[str, Any] = {}
    if payload.get("title"):
        fields[settings.bitable_name_field] = payload["title"]
    if payload.get("description"):
        fields[settings.bitable_requirement_field or settings.bitable_desc_field] = payload["description"]
    if payload.get("remark"):
        fields[settings.bitable_desc_field or settings.bitable_remark_field] = payload["remark"]
    if payload.get("category"):
        fields[settings.bitable_type_field] = payload["category"]
    divisions = payload.get("divisions") or []
    if divisions:
        fields[settings.bitable_division_field] = list(divisions)
    due = payload.get("due") or ""
    if due:
        try:
            dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_LOCAL_TZ)
            fields[settings.bitable_ddl_field] = int(dt.timestamp() * 1000)
        except ValueError:
            pass
    priority = (payload.get("priority") or "").strip().upper()
    if priority:
        fields[settings.bitable_priority_field] = _PRIORITY_TO_BITABLE.get(priority, priority)
    owner_ids = _assignee_ids(payload, owner_open_id)
    if owner_ids:
        fields[settings.bitable_owner_field] = [{"id": oid} for oid in owner_ids]
    if settings.bitable_status_field:
        fields[settings.bitable_status_field] = settings.bitable_default_status
    return fields


def _is_form_table(fields: list[dict[str, Any]]) -> bool:
    names = {str(f.get("field_name", "")).strip() for f in fields}
    return bool(names & {"Text", "Submitted on", "Respondents"}) and not (
        names & {"任务名称", "任务"}
    )


class LiveProvider(BaseProvider):
    """Calls the Feishu OpenAPI. User tokens come from the local token store;
    the tenant token is the fallback app identity."""

    def __init__(self, settings: Settings, db: DB) -> None:
        self.settings = settings
        self.db = db
        self.auth = AuthManager(settings)
        self.client = FeishuClient(
            settings.base_url,
            token_provider=self.auth.tenant_access_token,
        )

    def _user_token(self, open_id: str) -> str | None:
        if not open_id:
            return None
        token = self.db.get_token(open_id)
        if not token:
            return None
        if token.expires_at and token.expires_at < time.time() and token.refresh_token:
            try:
                refreshed = self.auth.refresh_user_token(token.refresh_token)
            except AuthError:
                return None
            token = TokenRecord(
                open_id=token.open_id,
                access_token=refreshed["access_token"],
                refresh_token=refreshed.get("refresh_token", token.refresh_token),
                expires_at=int(time.time() + refreshed.get("expires_in", 7200)),
                refresh_expires_at=int(time.time() + refreshed.get("refresh_token_expires_in", 0)),
                scope=refreshed.get("scope", ""),
            )
            self.db.save_token(token)
        return token.access_token

    def _token_or_none(self, open_id: str) -> str | None:
        return self._user_token(open_id)

    def list_tasks(self, open_id: str = "") -> list[TaskRecord]:
        items = task_api.list_tasks(self.client, token=self._token_or_none(open_id))
        out = []
        for item in items:
            local = self.db.get_task(item["guid"])
            out.append(_record_from_feishu(item, local.status if local else ""))
        return out

    def create_task(self, payload: dict[str, Any], open_id: str = "") -> TaskRecord:
        owner_ids = _assignee_ids(payload, open_id)
        if self.settings.bitable_submit_table_id:
            token = self._token_or_none(open_id)
            fields = _bitable_task_fields(payload, self.settings, open_id)
            try:
                table_fields = bitable_api.list_fields(
                    self.client, self.resolve_bitable_app_token(open_id),
                    self.settings.bitable_submit_table_id, token=token,
                )
            except Exception:  # noqa: BLE001 - fall back to configured columns
                table_fields = []
            if _is_form_table(table_fields):
                lines = [payload.get("title", "")]
                if payload.get("description"):
                    lines.append(payload["description"])
                if payload.get("due"):
                    lines.append(f"ddl: {payload['due']}")
                if payload.get("priority"):
                    lines.append(f"priority: {payload['priority']}")
                if owner_ids:
                    lines.append(f"assignee: {'、'.join(owner_ids)}")
                fields = {"Text": "\n".join(lines)}
            try:
                record = bitable_api.create_record(
                    self.client, self.resolve_bitable_app_token(open_id),
                    self.settings.bitable_submit_table_id, fields, token=token,
                )
                ev = bitable_api.record_to_event("", record)
                return TaskRecord(
                    guid=record.get("record_id") or "",
                    title=ev["title"] or payload.get("title", ""),
                    description=ev["description"] or payload.get("description", ""),
                    due=ev["due_iso"] or payload.get("due", ""),
                    priority=(payload.get("priority") or "NORMAL").upper(),
                    status="pending",
                    owner_open_id=owner_ids[0] if owner_ids else open_id,
                    owner_name="", creator="", url="",
                    created_at=now_iso(), updated_at=now_iso(), source="bitable",
                )
            except (ProviderError, FeishuAPIError) as exc:
                print(f"[create] Bitable submit failed ({exc}); falling back to Feishu task API")
        desc = (payload.get("description") or "").strip()
        extras = []
        if payload.get("category"):
            extras.append(f"兵种类型: {payload['category']}")
        if payload.get("divisions"):
            extras.append(f"研发组别: {'、'.join(payload['divisions'])}")
        if payload.get("remark"):
            extras.append(f"备注: {payload['remark']}")
        if extras:
            desc = (desc + "\n" + "\n".join(extras)).strip()
        item = task_api.create_task(
            self.client,
            summary=payload.get("title", ""),
            description=desc,
            due_iso=payload.get("due", ""),
            assignee_open_ids=owner_ids,
            token=self._token_or_none(open_id),
        )
        record = _record_from_feishu(item)
        record.priority = (payload.get("priority") or "NORMAL").upper()
        return record

    def update_task(self, guid: str, fields: dict[str, Any], open_id: str = "") -> TaskRecord:
        feishu_fields: dict[str, Any] = {}
        if "title" in fields:
            feishu_fields["summary"] = fields["title"]
        if "description" in fields:
            feishu_fields["description"] = fields["description"]
        if "due" in fields:
            feishu_fields["due_iso"] = fields["due"]
        if fields.get("status") == "completed":
            feishu_fields["completed"] = True
        item = task_api.update_task(self.client, guid, feishu_fields, token=self._token_or_none(open_id))
        record = _record_from_feishu(item, fields.get("status", ""))
        if "priority" in fields:
            record.priority = (fields["priority"] or "NORMAL").upper()
        return record

    def cancel_task(self, guid: str, open_id: str = "") -> TaskRecord:
        local = self.db.get_task(guid)
        if local and local.source == "bitable":
            return self._bitable_status_update(guid, "cancelled", open_id, local)
        task_api.complete_task(self.client, guid, token=self._token_or_none(open_id))
        local = local or self.db.get_task(guid)
        return TaskRecord(
            guid=guid, title=local.title if local else "", description=local.description if local else "",
            due=local.due if local else "", priority=local.priority if local else "NORMAL",
            status="cancelled", owner_open_id=local.owner_open_id if local else "",
            owner_name=local.owner_name if local else "", creator=local.creator if local else "",
            url=local.url if local else "", created_at=local.created_at if local else "",
            updated_at=now_iso(), source="feishu",
        )

    def complete_task(self, guid: str, open_id: str = "") -> TaskRecord:
        local = self.db.get_task(guid)
        if local and local.source == "bitable":
            return self._bitable_status_update(guid, "completed", open_id, local)
        item = task_api.complete_task(self.client, guid, token=self._token_or_none(open_id))
        return _record_from_feishu(item)

    def delete_task(self, guid: str, open_id: str = "") -> None:
        local = self.db.get_task(guid)
        if local and local.source == "bitable":
            if not self.settings.bitable_tasks_table_id:
                raise ProviderError(
                    "FEISHU_BITABLE_TASKS_TABLE_ID not set - cannot delete Bitable tasks from the website"
                )
            app_token = self.resolve_bitable_app_token(open_id)
            token = self._token_or_none(open_id)
            try:
                bitable_api.delete_record(
                    self.client, app_token, self.settings.bitable_tasks_table_id, guid, token=token,
                )
            except FeishuAPIError as exc:
                if exc.code != 99991679:
                    raise
                # The user token may lack base:record:delete while the app identity has it.
                bitable_api.delete_record(
                    self.client, app_token, self.settings.bitable_tasks_table_id, guid,
                    token=self.auth.tenant_access_token(),
                )
            return
        task_api.delete_task(self.client, guid, token=self._token_or_none(open_id))

    def _bitable_status_update(self, guid: str, status: str, open_id: str, local: TaskRecord | None) -> TaskRecord:
        if not self.settings.bitable_tasks_table_id:
            raise ProviderError(
                "FEISHU_BITABLE_TASKS_TABLE_ID not set - cannot update Bitable tasks from the website"
            )
        token = self._token_or_none(open_id)
        status_value = {"cancelled": "已放弃", "completed": "已完成"}.get(status, status)
        record = bitable_api.update_record(
            self.client, self.resolve_bitable_app_token(open_id),
            self.settings.bitable_tasks_table_id, guid,
            {self.settings.bitable_status_field: status_value}, token=token,
        )
        ev = bitable_api.record_to_event("", record)
        return TaskRecord(
            guid=guid, title=local.title if local else ev["title"],
            description=(local.description if local else ev["description"]),
            due=(local.due if local else ev["due_iso"]),
            priority=(local.priority if local else "NORMAL"),
            status=status, owner_open_id=local.owner_open_id if local else "",
            owner_name=local.owner_name if local else "", creator="", url="",
            created_at=local.created_at if local else "", updated_at=now_iso(), source="bitable",
        )

    def collect_messages(self, open_id: str = "") -> list[EventRecord]:
        token = self._token_or_none(open_id)
        chats: list[dict[str, Any]]
        if self.settings.chat_ids:
            chats = [{"chat_id": cid, "name": cid} for cid in self.settings.chat_ids]
        else:
            chats = im_api.list_chats(self.client, token=token)
        events: list[EventRecord] = []
        for chat in chats:
            chat_id = chat.get("chat_id") or chat.get("chat_id", "")
            chat_name = chat.get("name") or chat_id
            for msg in im_api.list_messages(self.client, chat_id, token=token):
                events.append(EventRecord(
                    source="message",
                    source_id=msg["message_id"],
                    title=f"[{chat_name}] {msg['text'][:80]}",
                    description=msg["text"],
                    ts=msg["ts_iso"],
                    author=msg["sender_id"],
                    url=chat.get("url", ""),
                    importance=2 if _looks_important(msg["text"]) else 1,
                    tags=["group_chat", chat_name],
                    raw=msg.get("raw", {}),
                ))
        return events

    def collect_meetings(self, open_id: str = "") -> list[EventRecord]:
        token = self._token_or_none(open_id)
        calendar_id = self.settings.calendar_id
        if not calendar_id:
            calendars = cal_api.list_calendars(self.client, token=token)
            calendar_id = calendars[0]["calendar_id"] if calendars else ""
        if not calendar_id:
            return []
        events: list[EventRecord] = []
        for ev in cal_api.list_events(self.client, calendar_id, token=token):
            events.append(EventRecord(
                source="meeting",
                source_id=ev["event_id"],
                title=ev["summary"] or "Meeting",
                description=ev["description"] or "",
                ts=ev["start_iso"],
                author="",
                url=ev["url"],
                importance=2 if _looks_important(ev["summary"] + " " + ev["description"]) else 1,
                tags=["meeting"],
                raw=ev.get("raw", {}),
            ))
        return events

    def resolve_bitable_app_token(self, open_id: str = "") -> str:
        """Return the base app_token: configured directly, or resolved from a wiki node."""
        app_token = self.settings.bitable_app_token
        if app_token:
            return app_token
        if not self.settings.wiki_node_token:
            raise ProviderError(
                "Bitable not configured - set FEISHU_BITABLE_APP_TOKEN (base URL app_token) "
                "or FEISHU_WIKI_NODE_TOKEN (wiki URL token) in .env"
            )
        token = self._token_or_none(open_id)
        node = wiki_api.get_node(self.client, self.settings.wiki_node_token, token=token)
        obj_token = node.get("obj_token") or ""
        if node.get("obj_type") != "bitable" or not obj_token:
            raise ProviderError(
                f"wiki node {self.settings.wiki_node_token} resolves to obj_type="
                f"{node.get('obj_type')!r} (expected 'bitable')"
            )
        return obj_token

    def task_create_options(self, open_id: str = "") -> dict[str, list[str]]:
        """Select-option lists for the task creation form (cached 5 min)."""
        key = f"{self.settings.bitable_app_token}|{self.settings.bitable_tasks_table_id}"
        cached = _task_options_cache.get(key)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        options = {k: list(v) for k, v in DEFAULT_TASK_OPTIONS.items()}
        try:
            fields = bitable_api.list_fields(
                self.client, self.resolve_bitable_app_token(open_id),
                self.settings.bitable_tasks_table_id, token=self._token_or_none(open_id),
            )
            for field in fields:
                names = [o.get("name") for o in ((field.get("property") or {}).get("options") or []) if o.get("name")]
                if field.get("field_name") == self.settings.bitable_type_field and names:
                    options["types"] = names
                elif field.get("field_name") == self.settings.bitable_division_field and names:
                    options["divisions"] = names
                elif field.get("field_name") == self.settings.bitable_priority_field and names:
                    options["priorities"] = names
        except Exception:  # noqa: BLE001 - fall back to static defaults on API failure
            pass
        _task_options_cache[key] = (time.time(), options)
        return options

    def collect_bitable(self, open_id: str = "") -> list[EventRecord]:
        """Collect records from the configured Bitable base (app_token or wiki node)."""
        token = self._token_or_none(open_id)
        app_token = self.resolve_bitable_app_token(open_id)
        tables = bitable_api.list_tables(self.client, app_token, token=token)[:5]
        events: list[EventRecord] = []
        for table in tables:
            table_id = table.get("table_id") or ""
            table_name = table.get("name") or table_id
            if not table_id:
                continue
            records = bitable_api.search_records(self.client, app_token, table_id, token=token)[:100]
            for record in records:
                ev = bitable_api.record_to_event(table_name, record)
                events.append(EventRecord(
                    source="bitable",
                    source_id=ev["record_id"] or f"{table_id}:{len(events)}",
                    title=f"[{table_name}] {ev['title'][:80]}",
                    description=ev["description"],
                    ts=ev["due_iso"],
                    author="",
                    url="",
                    importance=2 if (ev["due_iso"] or ev.get("priority") == "高") else 1,
                    tags=["bitable", table_name],
                    raw=record,
                ))
        return events

    def diagnostics(self, open_id: str = "") -> list[dict]:
        checks: list[dict] = []
        user_token: list[str] = []

        def add(name: str, fn) -> None:
            try:
                detail = fn()
                checks.append({"name": name, "ok": True, "detail": str(detail)[:200]})
            except Exception as exc:  # noqa: BLE001
                checks.append({"name": name, "ok": False, "detail": str(exc)[:300]})

        add("mode", lambda: self.settings.mode)
        add("tenant_access_token", lambda: "ok" if self.auth.tenant_access_token() else "empty")

        def check_user_token() -> str:
            token = self._user_token(open_id)
            user_token.append(token or "")
            return "present" if token else "absent - login through the website first"

        add("user_access_token", check_user_token)
        add("task list (my_tasks)", lambda: f"{len(self.list_tasks(open_id))} tasks")
        add("group chats (im.v1.chats)", lambda: (
            f"{len(im_api.list_chats(self.client, token=user_token[0] or self.auth.tenant_access_token()))} chats"
        ))
        add("calendar events", lambda: f"{len(self.collect_meetings(open_id))} events")
        add("bitable records", lambda: (
            f"{len(self.collect_bitable(open_id))} records"
            if self.settings.bitable_app_token or self.settings.wiki_node_token
            else "not configured (set FEISHU_BITABLE_APP_TOKEN or FEISHU_WIKI_NODE_TOKEN)"
        ))
        return checks


class MockProvider(BaseProvider):
    """Offline provider: never calls Feishu. State starts empty and persists
    to `data/mock_state.json` (git-ignored); no sample data is bundled."""

    def __init__(self, settings: Settings, db: DB, data_dir: Path | None = None) -> None:
        self.settings = settings
        self.db = db
        self.data_dir = data_dir or Path(settings.mock_data_dir or ROOT / "data")
        self.state_path = self.data_dir / "mock_state.json"
        self._load()

    def get_team_info(self) -> dict[str, Any]:
        return _load_json(self.data_dir / "team_info.json", {})

    def _load(self) -> None:
        raw = _load_json(self.state_path, {})
        if not isinstance(raw, dict):
            raw = {}
        self.state = {
            "tasks": raw.get("tasks", []),
            "messages": raw.get("messages", []),
            "meetings": raw.get("meetings", []),
        }

    def task_create_options(self, open_id: str = "") -> dict[str, list[str]]:
        return {k: list(v) for k, v in DEFAULT_TASK_OPTIONS.items()}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _user(self) -> UserRecord:
        info = self.get_team_info()
        demo = info.get("demo_user") or {}
        return UserRecord(
            open_id=demo.get("open_id", "ou_demo_user"),
            name=demo.get("name", "Demo User"),
            email=demo.get("email", "demo@example.com"),
            is_admin=True,
        )

    def _record(self, item: dict[str, Any]) -> TaskRecord:
        return TaskRecord(
            guid=str(item["guid"]),
            title=item.get("title") or "(untitled)",
            description=item.get("description") or "",
            due=item.get("due") or "",
            priority=item.get("priority") or "NORMAL",
            status=item.get("status") or "pending",
            owner_open_id=item.get("owner_open_id") or "",
            owner_name=item.get("owner_name") or "",
            creator=item.get("creator") or "",
            url=item.get("url") or "",
            created_at=item.get("created_at") or "",
            updated_at=item.get("updated_at") or "",
            source="mock",
        )

    def list_tasks(self, open_id: str = "") -> list[TaskRecord]:
        return [self._record(t) for t in self.state["tasks"]]

    def create_task(self, payload: dict[str, Any], open_id: str = "") -> TaskRecord:
        user = self._user()
        owner_ids = _assignee_ids(payload, user.open_id)
        item = {
            "guid": f"mock_{uuid.uuid4().hex[:12]}",
            "title": payload.get("title", ""),
            "description": payload.get("description", ""),
            "due": payload.get("due", ""),
            "priority": (payload.get("priority") or "NORMAL").upper(),
            "status": "pending",
            "owner_open_id": owner_ids[0] if owner_ids else user.open_id,
            "owner_open_ids": owner_ids,
            "owner_name": payload.get("owner_name") or user.name,
            "creator": user.open_id,
            "url": "",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        self.state["tasks"].append(item)
        self._save()
        return self._record(item)

    def update_task(self, guid: str, fields: dict[str, Any], open_id: str = "") -> TaskRecord:
        item = self._find(guid)
        for key in ("title", "description", "due", "priority", "status"):
            if key in fields:
                item[key] = fields[key]
        item["updated_at"] = now_iso()
        self._save()
        return self._record(item)

    def cancel_task(self, guid: str, open_id: str = "") -> TaskRecord:
        return self.update_task(guid, {"status": "cancelled"}, open_id)

    def complete_task(self, guid: str, open_id: str = "") -> TaskRecord:
        return self.update_task(guid, {"status": "completed"}, open_id)

    def delete_task(self, guid: str, open_id: str = "") -> None:
        self.state["tasks"] = [t for t in self.state["tasks"] if str(t["guid"]) != guid]
        self._save()

    def _find(self, guid: str) -> dict[str, Any]:
        for t in self.state["tasks"]:
            if str(t["guid"]) == guid:
                return t
        raise ProviderError(f"task not found: {guid}")

    def collect_messages(self, open_id: str = "") -> list[EventRecord]:
        out = []
        for m in self.state["messages"]:
            out.append(EventRecord(
                source="message",
                source_id=m.get("message_id", uuid.uuid4().hex),
                title=f"[{m.get('chat_name', 'group')}] {m.get('text', '')[:80]}",
                description=m.get("text", ""),
                ts=m.get("ts", ""),
                author=m.get("author", ""),
                url=m.get("url", ""),
                importance=m.get("importance", 1),
                tags=["group_chat", m.get("chat_name", "group")],
                raw=m,
            ))
        return out

    def collect_meetings(self, open_id: str = "") -> list[EventRecord]:
        out = []
        for m in self.state["meetings"]:
            out.append(EventRecord(
                source="meeting",
                source_id=m.get("event_id", uuid.uuid4().hex),
                title=m.get("title", "Meeting"),
                description=m.get("description", ""),
                ts=m.get("start_iso", ""),
                author=m.get("author", ""),
                url=m.get("url", ""),
                importance=m.get("importance", 1),
                tags=["meeting", m.get("meeting_type", "sync")],
                raw=m,
            ))
        return out

    def diagnostics(self, open_id: str = "") -> list[dict]:
        checks = super().diagnostics(open_id)
        checks.append({"name": "mock tasks", "ok": True, "detail": f"{len(self.list_tasks())} tasks"})
        checks.append({"name": "mock messages", "ok": True, "detail": f"{len(self.state['messages'])} messages"})
        checks.append({"name": "mock meetings", "ok": True, "detail": f"{len(self.state['meetings'])} meetings"})
        return checks


IMPORTANT_KEYWORDS = [
    "重要", "紧急", "马上", "尽快", "deadline", "截止", "ddl", "发布", "比赛", "晋级",
    "评审", "会议", "开会", "同步", "阻塞", "风险", "问题", "bug", "失败", "待办",
    "milestone", "milestone", "merge", "pr", "fix", "完成", "done", "ship", "release",
]


def _looks_important(text: str) -> bool:
    low = text.lower()
    return any(kw.lower() in low for kw in IMPORTANT_KEYWORDS)


def build_provider(settings: Settings, db: DB) -> BaseProvider:
    if settings.is_live:
        return LiveProvider(settings, db)
    return MockProvider(settings, db)
