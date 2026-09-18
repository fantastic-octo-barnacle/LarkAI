"""End-to-end smoke tests using the Flask test client in mock mode."""

from __future__ import annotations

import tempfile
import shutil
import unittest
import json
import socket
import threading
from pathlib import Path

from rmtask.config import Settings
from rmtask.notify import Emailer, notify_important_digest, notify_task_change
from rmtask.storage.models import TaskRecord, UserRecord
from rmtask.storage.db import DB
from rmtask.collector.pipeline import CollectResult, collect_all
from rmtask.collector.summarizer import group_by_day, group_by_source, timeline_rows
from rmtask.collector.team import derive_team_info
from rmtask.providers import BaseProvider
from rmtask.storage.models import EventRecord
from rmtask.notify.service import maybe_send_digest
from rmtask.web.app import create_app


def make_app(tmpdir: str) -> tuple:
    fixtures = Path(__file__).parent / "fixtures"
    for name in ("team_info.json", "sample_tasks.json", "sample_messages.json", "sample_meetings.json"):
        shutil.copy(fixtures / name, Path(tmpdir) / name)
    settings = Settings(
        mode="mock",
        db_path=str(Path(tmpdir) / "test.db"),
        mock_data_dir=tmpdir,
        secret_key="test",
    )
    db = DB(settings.db_path)
    db.init()
    app = create_app(settings)
    return app, db


class SmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.app, self.db = make_app(self.tmp)
        self.client = self.app.test_client()

    def login(self) -> None:
        resp = self.client.get("/login", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

    def test_index(self) -> None:
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"RoboMaster Research Team", resp.data)

    def test_login_and_sync(self) -> None:
        self.login()
        resp = self.client.post("/sync", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        tasks = self.db.list_tasks()
        self.assertGreaterEqual(len(tasks), 7)
        events = self.db.list_events()
        self.assertGreaterEqual(len(events), 15)

    def test_create_cancel_complete(self) -> None:
        self.login()
        resp = self.client.post(
            "/tasks/new",
            data={"title": "Write test plan", "description": "desc", "priority": "HIGH",
                  "due": "2026-09-30T10:00", "owner_open_id": "ou_demo_user"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        task = next(t for t in self.db.list_tasks() if t.title == "Write test plan")
        self.assertEqual(task.status, "pending")
        notifications = self.db.list_notifications()
        self.assertTrue(any(n["kind"] == "task_created" for n in notifications))

        resp = self.client.post(f"/tasks/{task.guid}/cancel", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        task = self.db.get_task(task.guid)
        self.assertEqual(task.status, "cancelled")

        resp = self.client.post(f"/tasks/{task.guid}/complete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        task = self.db.get_task(task.guid)
        self.assertEqual(task.status, "completed")

    def test_json_apis(self) -> None:
        self.login()
        for path in ("/api/stats.json", "/api/timeline.json", "/api/team.json"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("application/json", resp.content_type)

    def test_important_digest(self) -> None:
        notify_important_digest(
            self.db, Emailer(self.app.config["SETTINGS"]), self.app.config["SETTINGS"],
            items=[{"source": "message", "title": "Deadline changed", "ts": "2026-09-15T00:00:00+00:00"}],
        )
        rows = self.db.list_notifications()
        self.assertTrue(any(r["kind"] == "digest_important" for r in rows))

    def test_diagnostics_page(self) -> None:
        self.login()
        resp = self.client.get("/diagnostics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Diagnostics", resp.data)

    def test_timeline_show_filter(self) -> None:
        self.login()
        self.client.post("/sync")
        resp = self.client.get("/timeline?show=task&group=day")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"tl-axis", resp.data)
        self.assertEqual(resp.data.count(b"src-message"), 0)
        resp = self.client.get("/timeline?show=message,meeting,bitable&group=day")
        self.assertGreater(resp.data.count(b"src-message"), 0)

    def test_tasks_grouped_blocks(self) -> None:
        self.login()
        self.client.post("/sync")
        for group in ("status", "source", "division", "none"):
            resp = self.client.get(f"/tasks?group={group}")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"task-group", resp.data)

    def test_assignee_picker(self) -> None:
        self.login()
        self.client.post("/sync")
        resp = self.client.get("/tasks")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'name="owner_open_id"', resp.data)
        self.assertIn("步兵（HKU）".encode(), resp.data)
        self.assertIn(b'name="category"', resp.data)
        self.assertIn(b'name="divisions"', resp.data)
        members = self.client.get("/api/members.json").get_json()
        self.assertTrue(any(m["open_id"] == "ou_vision" for m in members))


class GroupingTest(unittest.TestCase):
    def _rows(self) -> list:
        return timeline_rows([
            EventRecord(source="message", source_id="m1", title="hi", ts="2026-09-15T08:00:00+00:00",
                        tags=["group_chat", "步兵"]),
            EventRecord(source="task", source_id="t1", title="Turret", ts="2026-09-15T10:00:00+00:00"),
            EventRecord(source="task", source_id="t2", title="Vision", ts="2026-09-16T10:00:00+00:00"),
        ])

    def test_group_by_day(self) -> None:
        days = group_by_day(self._rows())
        self.assertEqual([d["day"] for d in days], ["2026-09-16", "2026-09-15"])
        self.assertEqual(len(days[0]["items"]), 1)
        self.assertEqual(len(days[1]["items"]), 2)

    def test_group_by_source(self) -> None:
        groups = group_by_source(self._rows())
        self.assertEqual([g["source"] for g in groups], ["task", "message"])
        self.assertEqual(len(groups[0]["items"]), 2)


class PipelineResilienceTest(unittest.TestCase):
    def test_partial_collection_keeps_team_groups(self) -> None:
        tmp = tempfile.mkdtemp()
        db = DB(str(Path(tmp) / "test.db"))
        db.init()
        db.set_setting("team_live", json.dumps(
            {"groups": ["步兵"], "members": [], "facts": {"Groups": "1", "Members": "0", "Divisions": "-"}},
            ensure_ascii=False,
        ))

        class BrokenChats(BaseProvider):
            settings = Settings(mode="live")

            def list_tasks(self, open_id: str = "") -> list:
                return []

            def collect_messages(self, open_id: str = "") -> list:
                raise RuntimeError("scope missing")

            def collect_meetings(self, open_id: str = "") -> list:
                return []

            def collect_bitable(self, open_id: str = "") -> list:
                return []

        result = collect_all(db, BrokenChats(), open_id="")
        self.assertTrue(any("group_chat" in w for w in result.warnings))
        team = json.loads(db.get_setting("team_live"))
        self.assertEqual(team["facts"]["Groups"], "1")


class _MiniSMTP:
    """Minimal loopback SMTP server that captures the DATA payload."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(1)
        self.received: list[bytes] = []
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _serve(self) -> None:
        conn, _ = self.sock.accept()
        f = conn.makefile("rb")
        conn.sendall(b"220 localhost ESMTP test\r\n")
        data_mode = False
        buf = b""
        while True:
            line = f.readline()
            if not line:
                break
            if data_mode:
                if line == b".\r\n":
                    self.received.append(buf)
                    buf = b""
                    data_mode = False
                    conn.sendall(b"250 OK queued\r\n")
                else:
                    buf += line
                continue
            cmd = line.decode(errors="replace").strip().upper()
            if cmd.startswith(("EHLO", "HELO")):
                conn.sendall(b"250-localhost\r\n250 OK\r\n")
            elif cmd.startswith("MAIL FROM") or cmd.startswith("RCPT TO"):
                conn.sendall(b"250 OK\r\n")
            elif cmd.startswith("DATA"):
                data_mode = True
                conn.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
            elif cmd.startswith("QUIT"):
                conn.sendall(b"221 Bye\r\n")
                break
            else:
                conn.sendall(b"250 OK\r\n")
        conn.close()

    def close(self) -> None:
        self.sock.close()


class EmailerTest(unittest.TestCase):
    def _settings(self, **kw) -> Settings:
        base = dict(
            mode="live",
            email_from="rm@x.com",
            email_to=["a@x.com"],
            smtp_host="smtp.test",
            smtp_port=587,
            smtp_user="u",
            smtp_password="p",
            smtp_starttls=True,
            smtp_ssl=False,
        )
        base.update(kw)
        return Settings(**base)

    def test_dry_run_without_smtp(self) -> None:
        settings = Settings(email_from="", email_to=[])
        self.assertEqual(Emailer(settings).send("s", "<p>h</p>"), "dry_run")

    def test_send_uses_smtplib(self) -> None:
        from unittest import mock
        with mock.patch("rmtask.notify.emailer.smtplib.SMTP") as smtp:
            inst = smtp.return_value
            status = Emailer(self._settings()).send("Subject", "<b>Hi</b>", "Hi")
        self.assertEqual(status, "sent")
        smtp.assert_called_once_with("smtp.test", 587, timeout=20)
        inst.starttls.assert_called_once()
        inst.login.assert_called_once_with("u", "p")
        msg = inst.send_message.call_args.args[0]
        self.assertEqual(msg["Subject"], "Subject")
        self.assertEqual(msg["To"], "a@x.com")

    def test_email_smtp_end_to_end(self) -> None:
        try:
            probe = socket.socket()
            probe.close()
        except OSError:
            self.skipTest("loopback sockets unavailable in this sandbox")
        server = _MiniSMTP()
        server.start()
        try:
            settings = Settings(
                mode="live", email_from="rm@x.com", email_to=["a@x.com"],
                smtp_host="127.0.0.1", smtp_port=server.port,
                smtp_starttls=False, smtp_ssl=False, smtp_user="", smtp_password="",
            )
            status = Emailer(settings).send("Subject here", "<b>Hi</b>", "Hi")
        finally:
            server.close()
        self.assertEqual(status, "sent")
        raw = server.received[0]
        self.assertIn(b"Subject: Subject here", raw)
        self.assertIn(b"From: rm@x.com", raw)
        self.assertIn(b"To: a@x.com", raw)
        self.assertIn(b"<b>Hi</b>", raw)

    def test_send_includes_owner_email(self) -> None:
        from unittest import mock
        tmp = tempfile.mkdtemp()
        settings = self._settings()
        db = DB(str(Path(tmp) / "test.db"))
        db.init()
        db.upsert_user(UserRecord(open_id="ou_owner", name="Owner", email="owner@team.com"))
        task = TaskRecord(guid="g2", title="Turret", status="pending", owner_open_id="ou_owner")
        with mock.patch("rmtask.notify.emailer.smtplib.SMTP") as smtp:
            notify_task_change(db, Emailer(settings), settings, kind="created", task=task)
        msg = smtp.return_value.send_message.call_args.args[0]
        self.assertIn("owner@team.com", msg["To"])
        row = db.list_notifications()[0]
        self.assertIn("owner@team.com", row["recipients"])

    def test_failure_is_recorded_not_raised(self) -> None:
        from unittest import mock
        tmp = tempfile.mkdtemp()
        settings = self._settings()
        db = DB(str(Path(tmp) / "test.db"))
        db.init()
        task = TaskRecord(guid="g1", title="Turret", status="pending")
        with mock.patch("rmtask.notify.emailer.smtplib.SMTP") as smtp:
            smtp.return_value.send_message.side_effect = OSError("smtp down")
            notify_task_change(db, Emailer(settings), settings, kind="created", task=task)
        rows = db.list_notifications()
        self.assertEqual(rows[0]["kind"], "task_created")
        self.assertEqual(rows[0]["status"], "failed")
        self.assertIn("smtp down", rows[0]["error"])

    def test_auto_digest_only_sends_new_items(self) -> None:
        from datetime import datetime, timedelta, timezone
        from unittest import mock
        tmp = tempfile.mkdtemp()
        settings = self._settings()
        db = DB(str(Path(tmp) / "d.db"))
        db.init()

        def make_result(ts: str) -> CollectResult:
            return CollectResult(tasks=[], events=[], digest={"latest_important": [
                {"title": "X", "source": "message", "ts": ts, "importance": 3}]})

        now = datetime.now(timezone.utc)
        # baseline run: records the timestamp but sends nothing
        maybe_send_digest(db, settings, make_result(now.isoformat()))
        self.assertEqual(db.list_notifications(), [])
        self.assertTrue(db.get_setting("last_digest_ts"))
        # stale/same items: no email
        with mock.patch("rmtask.notify.emailer.smtplib.SMTP") as smtp:
            maybe_send_digest(db, settings, make_result(now.isoformat()))
        smtp.return_value.send_message.assert_not_called()
        # fresh item: digest email sent and audited
        fresh = (now + timedelta(minutes=5)).isoformat()
        with mock.patch("rmtask.notify.emailer.smtplib.SMTP") as smtp:
            maybe_send_digest(db, settings, make_result(fresh))
        smtp.return_value.send_message.assert_called_once()
        row = db.list_notifications()[0]
        self.assertEqual(row["kind"], "digest_important")
        self.assertEqual(row["status"], "sent")


class TeamDeriveTest(unittest.TestCase):
    def test_derive_team_info(self) -> None:
        events = [
            EventRecord(source="message", source_id="m1", title="hi", tags=["group_chat", "步兵"]),
            EventRecord(source="message", source_id="m2", title="hi", tags=["group_chat", "联队组"]),
        ]
        tasks = [
            TaskRecord(
                guid="r1", title="Turret", status="in_progress", source="bitable",
                owner_name="杨奕磊 李逸舟",
                description="record_id: r1 | 研发组别: 机械 | 负责人: 杨奕磊 李逸舟",
            ),
            TaskRecord(guid="r2", title="Vision", source="bitable", owner_name="邵一清",
                       description="研发组别: 算法 | 负责人: 邵一清"),
            TaskRecord(guid="r3", title="Chassis", source="bitable", owner_name="邵一清",
                       description="研发组别: 机械 硬件 | 负责人: 邵一清"),
        ]
        team = derive_team_info(tasks, events)
        self.assertEqual(team["facts"]["Groups"], "2")
        self.assertEqual(team["facts"]["Members"], "3")
        self.assertIn("机械", team["facts"]["Divisions"])
        self.assertIn("硬件", team["facts"]["Divisions"])
        names = {m["name"] for m in team["members"]}
        self.assertEqual(names, {"杨奕磊", "李逸舟", "邵一清"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
