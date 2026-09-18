"""SQLite persistence helper."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from rmtask.storage.models import EventRecord, TaskRecord, TokenRecord, UserRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    open_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    avatar_url TEXT NOT NULL DEFAULT '',
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    open_id TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL DEFAULT '',
    expires_at INTEGER NOT NULL DEFAULT 0,
    refresh_expires_at INTEGER NOT NULL DEFAULT 0,
    scope TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    guid TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    due TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'NORMAL',
    status TEXT NOT NULL DEFAULT 'pending',
    owner_open_id TEXT NOT NULL DEFAULT '',
    owner_name TEXT NOT NULL DEFAULT '',
    creator TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'feishu',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    ts TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    importance INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    raw TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    recipients TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'dry_run',
    error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


class DB:
    def __init__(self, path: str) -> None:
        self.path = str(path)

    @contextmanager
    def connect(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init(self, force: bool = False) -> None:
        with self.connect() as conn:
            if force:
                conn.executescript(
                    "DROP TABLE IF EXISTS users; DROP TABLE IF EXISTS oauth_tokens; "
                    "DROP TABLE IF EXISTS tasks; DROP TABLE IF EXISTS events; "
                    "DROP TABLE IF EXISTS notifications; DROP TABLE IF EXISTS settings;"
                )
            conn.executescript(SCHEMA)

    # -- users ---------------------------------------------------------------
    def upsert_user(self, user: UserRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO users(open_id, name, email, avatar_url, is_admin)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(open_id) DO UPDATE SET name=excluded.name,
                     email=CASE WHEN excluded.email != '' THEN excluded.email ELSE users.email END,
                     avatar_url=excluded.avatar_url, is_admin=excluded.is_admin""",
                (user.open_id, user.name, user.email, user.avatar_url, int(user.is_admin)),
            )

    def get_user(self, open_id: str) -> UserRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE open_id=?", (open_id,)).fetchone()
        if not row:
            return None
        return UserRecord(
            open_id=row["open_id"], name=row["name"], email=row["email"],
            avatar_url=row["avatar_url"], is_admin=bool(row["is_admin"]),
        )

    def list_users(self) -> list[UserRecord]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY is_admin DESC, open_id").fetchall()
        return [
            UserRecord(
                open_id=row["open_id"], name=row["name"], email=row["email"],
                avatar_url=row["avatar_url"], is_admin=bool(row["is_admin"]),
            )
            for row in rows
        ]

    def first_user_open_id(self) -> str:
        """OpenID of the (admin-first) user to reuse their stored token."""
        users = self.list_users()
        return users[0].open_id if users else ""

    # -- tokens ---------------------------------------------------------------
    def save_token(self, token: TokenRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO oauth_tokens(open_id, access_token, refresh_token, expires_at,
                                            refresh_expires_at, scope, updated_at)
                   VALUES(?,?,?,?,?,?, datetime('now'))
                   ON CONFLICT(open_id) DO UPDATE SET access_token=excluded.access_token,
                     refresh_token=excluded.refresh_token, expires_at=excluded.expires_at,
                     refresh_expires_at=excluded.refresh_expires_at, scope=excluded.scope,
                     updated_at=datetime('now')""",
                (token.open_id, token.access_token, token.refresh_token, token.expires_at,
                 token.refresh_expires_at, token.scope),
            )

    def get_token(self, open_id: str) -> TokenRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM oauth_tokens WHERE open_id=?", (open_id,)).fetchone()
        if not row:
            return None
        return TokenRecord(
            open_id=row["open_id"], access_token=row["access_token"], refresh_token=row["refresh_token"],
            expires_at=row["expires_at"], refresh_expires_at=row["refresh_expires_at"], scope=row["scope"],
        )

    # -- tasks ----------------------------------------------------------------
    def upsert_task(self, task: TaskRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO tasks(guid, title, description, due, priority, status, owner_open_id,
                                     owner_name, creator, url, source, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(guid) DO UPDATE SET title=excluded.title, description=excluded.description,
                     due=excluded.due, priority=excluded.priority, status=excluded.status,
                     owner_open_id=excluded.owner_open_id, owner_name=excluded.owner_name,
                     creator=excluded.creator, url=excluded.url, source=excluded.source,
                     updated_at=excluded.updated_at""",
                (task.guid, task.title, task.description, task.due, task.priority, task.status,
                 task.owner_open_id, task.owner_name, task.creator, task.url, task.source,
                 task.created_at, task.updated_at),
            )

    def list_tasks(self, status: str = "", search: str = "", limit: int = 200) -> list[TaskRecord]:
        sql = "SELECT * FROM tasks WHERE 1=1"
        params: list[str] = []
        if status:
            sql += " AND status=?"
            params.append(status)
        if search:
            sql += " AND (title LIKE ? OR description LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        sql += " ORDER BY due='' ASC, due ASC, created_at DESC LIMIT ?"
        params.append(str(limit))
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_task(r) for r in rows]

    def get_task(self, guid: str) -> TaskRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE guid=?", (guid,)).fetchone()
        return self._row_to_task(row) if row else None

    @staticmethod
    def _row_to_task(r: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            guid=r["guid"], title=r["title"], description=r["description"], due=r["due"],
            priority=r["priority"], status=r["status"], owner_open_id=r["owner_open_id"],
            owner_name=r["owner_name"], creator=r["creator"], url=r["url"], source=r["source"],
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    def delete_task(self, guid: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM tasks WHERE guid=?", (guid,))

    def purge_tasks(self, source: str) -> None:
        """Delete every task (and its mirrored task events) originating from `source`."""
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM events WHERE source='task' AND source_id IN "
                "(SELECT guid FROM tasks WHERE source=?)",
                (source,),
            )
            conn.execute("DELETE FROM events WHERE source=?", (source,))
            conn.execute("DELETE FROM tasks WHERE source=?", (source,))

    def prune_source(self, source: str, keep_guids: set[str]) -> None:
        """Remove `source` tasks/events whose guid no longer appears in `keep_guids`."""
        if not keep_guids:
            return
        guids = list(keep_guids)
        placeholders = ",".join("?" * len(guids))
        with self.connect() as conn:
            conn.execute(
                f"DELETE FROM events WHERE source=? AND source_id NOT IN ({placeholders})",
                [source, *guids],
            )
            conn.execute(
                f"DELETE FROM tasks WHERE source=? AND guid NOT IN ({placeholders})",
                [source, *guids],
            )

    # -- events ---------------------------------------------------------------
    def upsert_event(self, event: EventRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO events(source, source_id, title, description, ts, author, url,
                                      importance, tags, raw, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?, datetime('now'))
                   ON CONFLICT(source, source_id) DO UPDATE SET title=excluded.title,
                     description=excluded.description, ts=excluded.ts, author=excluded.author,
                     url=excluded.url, importance=excluded.importance, tags=excluded.tags,
                     raw=excluded.raw, updated_at=datetime('now')""",
                (event.source, event.source_id, event.title, event.description[:5000], event.ts,
                 event.author, event.url, event.importance, json.dumps(event.tags, ensure_ascii=False),
                 json.dumps(event.raw, ensure_ascii=False, default=str)[:20000]),
            )

    def list_events(self, source: str = "", search: str = "", limit: int = 300) -> list[EventRecord]:
        sql = "SELECT * FROM events WHERE 1=1"
        params: list[str] = []
        if source:
            sql += " AND source=?"
            params.append(source)
        if search:
            sql += " AND (title LIKE ? OR description LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(str(limit))
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            try:
                tags = json.loads(r["tags"])
                raw = json.loads(r["raw"])
            except (ValueError, TypeError):
                tags, raw = [], {}
            out.append(EventRecord(
                source=r["source"], source_id=r["source_id"], title=r["title"],
                description=r["description"], ts=r["ts"], author=r["author"], url=r["url"],
                importance=r["importance"], tags=tags, raw=raw,
            ))
        return out

    # -- notifications --------------------------------------------------------
    def add_notification(self, kind: str, subject: str, body: str, recipients: str,
                         status: str = "dry_run", error: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO notifications(kind, subject, body, recipients, status, error) VALUES(?,?,?,?,?,?)",
                (kind, subject, body, recipients, status, error),
            )

    def list_notifications(self, limit: int = 100):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?",
                                (limit,)).fetchall()

    # -- settings -----------------------------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
