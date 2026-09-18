"""Contract tests for the live Feishu wrappers (HTTP mocked, no credentials).

These lock the exact request shapes verified against the official docs:
  * authorize  - GET accounts.feishu.cn/open-apis/authen/v1/authorize
  * token     - POST accounts.feishu.cn/oauth/v3/token (form-urlencoded)
  * tasks     - list type=my_tasks / create / patch {task, update_fields} completed_at
  * im        - start_time/end_time in SECONDS
  * calendar  - timestamps in SECONDS (params and response)
"""

from __future__ import annotations

import json
import tempfile
import time
import types
import unittest
from pathlib import Path

from rmtask.api import AuthManager, FeishuClient
from rmtask.api import bitable as bitable_api
from rmtask.api import calendar as cal_api
from rmtask.api import contact as contact_api
from rmtask.api import im as im_api
from rmtask.api import tasks as task_api
from rmtask.config import Settings
from rmtask.errors import FeishuAPIError
from rmtask.providers import LiveProvider
from rmtask.storage.db import DB
from rmtask.storage.models import TaskRecord, TokenRecord


def fake_response(payload: dict):
    resp = types.SimpleNamespace()
    resp.json = lambda: payload
    resp.status_code = 200
    resp.text = json.dumps(payload)
    return resp


def ok(payload: dict) -> dict:
    return {"code": 0, "msg": "success", "data": payload}


class AuthContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            mode="live",
            app_id="cli_test123",
            app_secret="secret123",
            redirect_uri="https://rm.example.com/oauth/callback",
            scopes=["auth:user.id:read", "task:task:read", "offline_access"],
        )
        self.auth = AuthManager(self.settings)

    def test_authorize_url(self) -> None:
        url = self.auth.build_authorize_url("state123", scope="task:task:read offline_access")
        self.assertTrue(url.startswith("https://accounts.feishu.cn/open-apis/authen/v1/authorize?"))
        self.assertIn("client_id=cli_test123", url)
        self.assertIn("response_type=code", url)
        self.assertIn("redirect_uri=https%3A%2F%2Frm.example.com%2Foauth%2Fcallback", url)
        self.assertIn("scope=task%3Atask%3Aread+offline_access", url)
        self.assertIn("state=state123", url)

    def test_exchange_code_form_encoded(self) -> None:
        with __import__("unittest.mock").mock.patch("rmtask.api.auth.requests.post") as post:
            post.return_value = fake_response({
                "code": 0,
                "access_token": "u-token",
                "expires_in": 7200,
                "refresh_token": "r-token",
            })
            out = self.auth.exchange_code("code123")
        self.assertEqual(out["access_token"], "u-token")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://accounts.feishu.cn/oauth/v3/token")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/x-www-form-urlencoded")
        self.assertEqual(kwargs["data"]["grant_type"], "authorization_code")
        self.assertEqual(kwargs["data"]["client_id"], "cli_test123")
        self.assertEqual(kwargs["data"]["client_secret"], "secret123")
        self.assertEqual(kwargs["data"]["code"], "code123")

    def test_tenant_token_cache(self) -> None:
        with __import__("unittest.mock").mock.patch("rmtask.api.auth.requests.post") as post:
            post.side_effect = [
                fake_response({"code": 0, "tenant_access_token": "t-one", "expire": 7200}),
                fake_response({"code": 0, "tenant_access_token": "t-two", "expire": 7200}),
            ]
            first = self.auth.tenant_access_token()
            second = self.auth.tenant_access_token()
        self.assertEqual(first, "t-one")
        self.assertEqual(second, "t-one")
        self.assertEqual(post.call_count, 1)


class ClientResilienceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FeishuClient("https://open.feishu.cn")

    def test_retries_transient_network_error(self) -> None:
        import requests as _requests
        m = __import__("unittest.mock")
        with m.mock.patch("rmtask.api.base.time.sleep"), m.mock.patch(
            "rmtask.api.base.requests.request",
            side_effect=[_requests.exceptions.ConnectTimeout("blip"), fake_response(ok({"ok": True}))],
        ) as req:
            data = self.client.get("/healthz")
        self.assertEqual(req.call_count, 2)
        self.assertIn("ok", data)

    def test_network_error_raises_feishu_api_error(self) -> None:
        import requests as _requests
        m = __import__("unittest.mock")
        with m.mock.patch("rmtask.api.base.time.sleep"), m.mock.patch(
            "rmtask.api.base.requests.request",
            side_effect=_requests.exceptions.ConnectTimeout("down"),
        ) as req:
            with self.assertRaises(FeishuAPIError) as ctx:
                self.client.get("/healthz")
        self.assertEqual(req.call_count, 3)
        self.assertIn("Feishu network error", str(ctx.exception))


class TasksContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FeishuClient("https://open.feishu.cn")
        self.task = {
            "guid": "guid-1",
            "summary": "Calibrate vision",
            "description": "desc",
            "due": {"timestamp": "1675454764000", "is_all_day": False},
            "completed_at": "",
            "creator": {"id": "ou_creator", "type": "user", "role": "assignee"},
            "members": [{"id": "ou_assignee", "type": "user", "role": "assignee"}],
            "url": "https://applink.feishu.cn/client/todo/detail?guid=guid-1",
            "created_at": "1675000000000",
        }

    def _patch_request(self, payloads):
        from unittest.mock import patch
        return patch("rmtask.api.base.requests.request", side_effect=[fake_response(p) for p in payloads])

    def test_create_body(self) -> None:
        with self._patch_request([ok({"task": self.task})]) as req:
            item = task_api.create_task(
                self.client, summary="Calibrate vision", description="desc",
                due_iso="2023-02-04T06:06:04+00:00", assignee_open_id="ou_assignee",
            )
        self.assertEqual(item["guid"], "guid-1")
        args, kwargs = req.call_args
        self.assertTrue(args[1].endswith("/open-apis/task/v2/tasks"))
        body = kwargs["json"]
        self.assertEqual(body["summary"], "Calibrate vision")
        self.assertEqual(body["members"], [{"id": "ou_assignee", "type": "user", "role": "assignee"}])
        from datetime import datetime
        expected_ms = str(int(datetime.fromisoformat("2023-02-04T06:06:04+00:00").timestamp() * 1000))
        self.assertEqual(body["due"], {"timestamp": expected_ms, "is_all_day": False})
        self.assertIn("client_token", body)
        self.assertNotIn("priority", body)

    def test_patch_completed_wrapper(self) -> None:
        with self._patch_request([ok({"task": {**self.task, "completed_at": "1675497964000"}})]) as req:
            task_api.complete_task(self.client, "guid-1")
        _, kwargs = req.call_args
        body = kwargs["json"]
        self.assertEqual(list(body.keys()), ["task", "update_fields"])
        self.assertEqual(body["update_fields"], ["completed_at"])
        self.assertTrue(body["task"]["completed_at"].isdigit())
        self.assertGreater(int(body["task"]["completed_at"]), 10**12)

    def test_list_pagination_and_type(self) -> None:
        p1 = ok({"items": [self.task], "page_token": "next", "has_more": True})
        p2 = ok({"items": [{**self.task, "guid": "guid-2"}], "page_token": "", "has_more": False})
        calls = []

        def capture(*args, **kwargs):
            snapshot = dict(kwargs)
            snapshot["params"] = dict(kwargs.get("params") or {})
            calls.append((args, snapshot))
            return fake_response(p1 if len(calls) == 1 else p2)

        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   side_effect=capture):
            items = task_api.list_tasks(self.client)
        self.assertEqual([i["guid"] for i in items], ["guid-1", "guid-2"])
        self.assertEqual(calls[0][1]["params"].get("type"), "my_tasks")
        self.assertEqual(calls[0][1]["params"]["page_token"], "")
        self.assertEqual(calls[1][1]["params"]["page_token"], "next")

    def test_error_raised(self) -> None:
        with self._patch_request([{"code": 99991679, "msg": "Unauthorized"}]) as req:
            with self.assertRaises(FeishuAPIError) as ctx:
                task_api.list_tasks(self.client)
        self.assertEqual(ctx.exception.code, 99991679)


class ImCalendarContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FeishuClient("https://open.feishu.cn")

    def test_message_start_time_seconds(self) -> None:
        msg = {
            "message_id": "om_1",
            "msg_type": "text",
            "create_time": "1615380573411",
            "body": {"content": json.dumps({"text": "deadline tomorrow"})},
            "sender": {"id": "ou_x", "sender_type": "user"},
        }
        payload = ok({"items": [msg], "has_more": False, "page_token": ""})
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(payload)) as req:
            out = im_api.list_messages(self.client, "oc_1", start_iso="2026-09-15T00:00:00+00:00")
        params = req.call_args.kwargs["params"]
        from datetime import datetime
        expected = str(int(datetime.fromisoformat("2026-09-15T00:00:00+00:00").timestamp()))
        self.assertEqual(params["start_time"], expected)
        self.assertLess(int(params["start_time"]), 10**10)  # seconds, not ms
        self.assertEqual(out[0]["text"], "deadline tomorrow")

    def test_calendar_timestamps_seconds(self) -> None:
        ev = {
            "event_id": "ev_1",
            "summary": "Weekly sync",
            "description": "agenda",
            "start_time": {"timestamp": "1602504000"},
            "end_time": {"timestamp": "1602507600"},
        }
        payload = ok({"items": [ev], "has_more": False, "page_token": ""})
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(payload)) as req:
            out = cal_api.list_events(self.client, "cal_1")
        self.assertEqual(out[0]["start_iso"], "2020-10-12T12:00:00+00:00")
        self.assertEqual(out[0]["end_iso"], "2020-10-12T13:00:00+00:00")
        self.assertEqual(req.call_args.kwargs["params"].get("start_time", None), None)


class BitableContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FeishuClient("https://open.feishu.cn")

    def test_list_tables(self) -> None:
        payload = ok({"items": [{"table_id": "tbl_1", "name": "任务表"}], "has_more": False, "page_token": ""})
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(payload)) as req:
            tables = bitable_api.list_tables(self.client, "app_1")
        self.assertEqual(tables[0]["table_id"], "tbl_1")
        self.assertTrue(req.call_args.args[1].endswith("/open-apis/bitable/v1/apps/app_1/tables"))

    def test_list_fields(self) -> None:
        payload = ok({"items": [{"field_name": "任务名称", "type": 1}], "has_more": False, "page_token": ""})
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(payload)) as req:
            fields = bitable_api.list_fields(self.client, "app_1", "tbl_1")
        self.assertEqual(fields[0]["field_name"], "任务名称")
        self.assertTrue(req.call_args.args[1].endswith("/open-apis/bitable/v1/apps/app_1/tables/tbl_1/fields"))

    def test_search_records_post(self) -> None:
        record = {"record_id": "rec_1", "fields": {"任务": "Calibrate", "截止日期": 1788393600000}}
        payload = ok({"items": [record], "has_more": False, "page_token": ""})
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(payload)) as req:
            records = bitable_api.search_records(self.client, "app_1", "tbl_1")
        self.assertEqual(records[0]["record_id"], "rec_1")
        self.assertEqual(req.call_args.args[0], "POST")
        self.assertEqual(req.call_args.kwargs["params"]["page_size"], 100)

    def test_record_to_event_heuristics(self) -> None:
        record = {"record_id": "rec_1", "fields": {"任务": "Calibrate camera", "截止日期": "2026-10-01"}}
        ev = bitable_api.record_to_event("任务表", record)
        self.assertEqual(ev["title"], "Calibrate camera")
        self.assertTrue(ev["due_iso"].startswith("2026-10-01"))
        self.assertIn("任务: Calibrate camera", ev["description"])

    def test_record_to_event_prefers_notes_over_raw_dump(self) -> None:
        record = {"record_id": "rec_9", "fields": {
            "任务名称": [{"text": "Build turret", "type": "text"}],
            "备注": "Only the turret, not the chassis",
            "父记录": {},
        }}
        ev = bitable_api.record_to_event("任务管理表", record)
        self.assertEqual(ev["description"], "Only the turret, not the chassis")
        self.assertNotIn("父记录", ev["description"])

    def test_record_to_event_ddl_and_title_preference(self) -> None:
        record = {"record_id": "rec_2", "fields": {
            "任务ID": "017",
            "任务名称": [{"text": "Hello World", "type": "text"}],
            "ddl": 1785427200000,
            "优先级": "高",
        }}
        ev = bitable_api.record_to_event("任务管理表", record)
        self.assertEqual(ev["title"], "Hello World")
        self.assertTrue(ev["due_iso"].startswith("2026-"))
        self.assertEqual(ev["priority"], "高")

    def test_record_to_task_maps_status_priority_owner(self) -> None:
        record = {"record_id": "rec_3", "fields": {
            "任务名称": [{"text": "Build turret", "type": "text"}],
            "ddl": 1785427200000,
            "任务状态（由技术组长验收）": "执行中",
            "优先级": "高",
            "负责人": [{"id": "ou_a", "name": "Alice"}, {"name": "Bob"}],
        }}
        t = bitable_api.record_to_task(record, "任务管理表")
        self.assertEqual(t["guid"], "rec_3")
        self.assertEqual(t["title"], "Build turret")
        self.assertEqual(t["status"], "in_progress")
        self.assertEqual(t["priority"], "HIGH")
        self.assertEqual(t["owner_open_ids"], ["ou_a"])
        self.assertIn("Alice", t["owner_names"])
        self.assertIn("Bob", t["owner_names"])

    def test_record_to_task_skips_parent_rows(self) -> None:
        parent = {"record_id": "rec_4", "fields": {"任务ID": "034", "兵种类型": ["步兵"], "父记录": {}}}
        self.assertEqual(bitable_api.record_to_task(parent, "任务管理表"), {})

    def test_create_record_post_shape(self) -> None:
        record = {"record_id": "rec_new", "fields": {"任务名称": [{"text": "New tank", "type": "text"}]}}
        payload = ok({"record": record})
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(payload)) as req:
            out = bitable_api.create_record(self.client, "app_1", "tbl_submit", {"任务名称": "New tank"})
        self.assertEqual(out["record_id"], "rec_new")
        self.assertEqual(req.call_args.args[0], "POST")
        self.assertTrue(req.call_args.args[1].endswith("/apps/app_1/tables/tbl_submit/records"))
        self.assertEqual(req.call_args.kwargs["json"], {"fields": {"任务名称": "New tank"}})

    def test_update_record_put_shape(self) -> None:
        record = {"record_id": "rec_1", "fields": {"任务状态（由技术组长验收）": "已取消"}}
        payload = ok({"record": record})
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(payload)) as req:
            out = bitable_api.update_record(self.client, "app_1", "tbl_tasks", "rec_1",
                                            {"任务状态（由技术组长验收）": "已取消"})
        self.assertEqual(req.call_args.args[0], "PUT")
        self.assertTrue(req.call_args.args[1].endswith("/apps/app_1/tables/tbl_tasks/records/rec_1"))
        self.assertEqual(req.call_args.kwargs["json"], {"fields": {"任务状态（由技术组长验收）": "已取消"}})

    def test_delete_record(self) -> None:
        payload = ok({})
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(payload)) as req:
            bitable_api.delete_record(self.client, "app_1", "tbl_1", "rec_9")
        self.assertEqual(req.call_args.args[0], "DELETE")
        self.assertTrue(req.call_args.args[1].endswith(
            "/open-apis/bitable/v1/apps/app_1/tables/tbl_1/records/rec_9"))

    def test_bitable_task_field_mapping(self) -> None:
        from rmtask.providers import _bitable_task_fields
        settings = Settings()
        fields = _bitable_task_fields(
            {"title": "Build turret", "description": "desc", "due": "2026-10-01T10:00:00+00:00",
             "priority": "HIGH", "owner_open_id": "ou_x", "category": "总车组",
             "divisions": ["机械"], "remark": "note"},
            settings, "ou_me",
        )
        self.assertEqual(fields["任务名称"], "Build turret")
        self.assertEqual(fields["任务需求（兵种组长填写）（务必详细！）"], "desc")
        self.assertEqual(fields["兵种类型"], "总车组")
        self.assertEqual(fields["研发组别"], ["机械"])
        self.assertEqual(fields["备注"], "note")
        self.assertEqual(fields["优先级"], "高")
        self.assertEqual(fields["负责人"], [{"id": "ou_x"}])
        self.assertEqual(fields["任务状态（由技术组长验收）"], "待执行")
        self.assertIn("ddl", fields)
        self.assertGreater(fields["ddl"], 10**12)

    def test_bitable_task_fields_naive_due_uses_local_offset(self) -> None:
        from datetime import datetime
        from rmtask.providers import _LOCAL_TZ, _bitable_task_fields
        fields = _bitable_task_fields({"title": "T", "due": "2026-10-05T18:00:00"}, Settings(), "")
        expected = int(datetime(2026, 10, 5, 18, 0, 0, tzinfo=_LOCAL_TZ).timestamp() * 1000)
        self.assertEqual(fields["ddl"], expected)

class ContactContractTest(unittest.TestCase):
    def test_get_user(self) -> None:
        client = FeishuClient("https://open.feishu.cn")
        payload = ok({"user": {"open_id": "ou_x", "name": "郭宝", "email": "guo@example.com"}})
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(payload)) as req:
            user = contact_api.get_user(client, "ou_x", token="t")
        self.assertEqual(user["email"], "guo@example.com")
        self.assertEqual(req.call_args.args[0], "GET")
        self.assertTrue(req.call_args.args[1].endswith("/open-apis/contact/v3/users/ou_x"))
        self.assertEqual(req.call_args.kwargs["params"], {"user_id_type": "open_id"})


class ProviderRoutingTest(unittest.TestCase):
    def _provider(self, **kw) -> LiveProvider:
        settings = Settings(
            mode="live", app_id="cli_test", app_secret="secret",
            redirect_uri="https://rm.example.com/oauth/callback",
            scopes=["auth:user.id:read", "offline_access"],
            bitable_app_token="app_1",
            **kw,
        )
        db = DB(str(Path(tempfile.mkdtemp()) / "t.db"))
        db.init()
        db.save_token(TokenRecord(
            open_id="ou_me", access_token="u-token",
            expires_at=int(time.time()) + 7200,
        ))
        return LiveProvider(settings, db)

    def test_create_task_routes_to_bitable_when_configured(self) -> None:
        provider = self._provider(bitable_submit_table_id="tbl_submit")
        record = {"record_id": "rec_new", "fields": {"任务名称": [{"text": "Fly", "type": "text"}]}}
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(ok({"record": record}))) as req:
            task = provider.create_task(
                {"title": "Fly", "priority": "URGENT", "due": "2026-09-20T10:00:00+00:00",
                 "description": "Detailed requirement", "category": "步兵（HKU）",
                 "divisions": ["机械", "算法"], "remark": "note"},
                open_id="ou_me",
            )
        self.assertEqual(task.source, "bitable")
        self.assertEqual(task.guid, "rec_new")
        self.assertTrue(req.call_args.args[1].endswith(
            "/open-apis/bitable/v1/apps/app_1/tables/tbl_submit/records"))
        fields = req.call_args.kwargs["json"]["fields"]
        self.assertEqual(fields["任务名称"], "Fly")
        self.assertEqual(fields["优先级"], "高")
        self.assertEqual(fields["兵种类型"], "步兵（HKU）")
        self.assertEqual(fields["研发组别"], ["机械", "算法"])
        self.assertEqual(fields["任务需求（兵种组长填写）（务必详细！）"], "Detailed requirement")
        self.assertEqual(fields["备注"], "note")
        self.assertEqual(fields["负责人"], [{"id": "ou_me"}])
        self.assertIn("ddl", fields)

    def test_create_task_falls_back_to_task_v2(self) -> None:
        provider = self._provider()
        item = {"guid": "g1", "summary": "Fly", "description": "", "due": None,
                "completed_at": "", "creator": {"id": "ou_me"}, "members": [], "url": ""}
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(ok({"task": item}))) as req:
            task = provider.create_task({"title": "Fly"}, open_id="ou_me")
        self.assertEqual(task.source, "feishu")
        self.assertTrue(req.call_args.args[1].endswith("/open-apis/task/v2/tasks"))

    def test_create_task_falls_back_to_task_v2_when_bitable_scope_missing(self) -> None:
        provider = self._provider(bitable_submit_table_id="tbl_submit")
        field_payload = ok({"items": [{"field_name": "任务名称"}], "has_more": False, "page_token": ""})
        denied = {"code": 99991679, "msg": "required one of these privileges under the user identity: "
                                          "[bitable:app, base:record:create]", "data": None}
        item = {"guid": "g_fb", "summary": "Fly", "description": "", "due": None,
                "completed_at": "", "creator": {"id": "ou_me"}, "members": [], "url": ""}
        with __import__("unittest.mock").mock.patch(
            "rmtask.api.base.requests.request",
            side_effect=[fake_response(field_payload), fake_response(denied),
                         fake_response(ok({"task": item}))],
        ) as req:
            task = provider.create_task({"title": "Fly"}, open_id="ou_me")
        self.assertEqual(task.source, "feishu")
        self.assertEqual(task.guid, "g_fb")
        self.assertTrue(req.call_args.args[1].endswith("/open-apis/task/v2/tasks"))

    def test_create_task_adapts_to_form_submit_table(self) -> None:
        provider = self._provider(bitable_submit_table_id="tbl_form")
        field_payload = ok({"items": [
            {"field_name": "Text"}, {"field_name": "Submitted on"}, {"field_name": "Respondents"},
        ], "has_more": False, "page_token": ""})
        record = {"record_id": "rec_f1", "fields": {"Text": "Fly"}}
        with __import__("unittest.mock").mock.patch(
            "rmtask.api.base.requests.request",
            side_effect=[fake_response(field_payload), fake_response(ok({"record": record}))],
        ) as req:
            task = provider.create_task(
                {"title": "Fly", "priority": "HIGH", "due": "2026-09-20T10:00:00+00:00"},
                open_id="ou_me",
            )
        self.assertEqual(task.source, "bitable")
        self.assertEqual(task.guid, "rec_f1")
        body = req.call_args_list[-1].kwargs["json"]
        self.assertIn("Text", body["fields"])
        self.assertNotIn("任务名称", body["fields"])
        self.assertIn("Fly", body["fields"]["Text"])

    def test_delete_task_routes_to_bitable(self) -> None:
        provider = self._provider(bitable_tasks_table_id="tbl_tasks")
        provider.db.upsert_task(TaskRecord(
            guid="rec_x", title="Turret", status="pending", source="bitable",
        ))
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(ok({}))) as req:
            provider.delete_task("rec_x", open_id="ou_me")
        self.assertEqual(req.call_args.args[0], "DELETE")
        self.assertTrue(req.call_args.args[1].endswith(
            "/open-apis/bitable/v1/apps/app_1/tables/tbl_tasks/records/rec_x"))

    def test_delete_bitable_falls_back_to_tenant_token_on_permission_error(self) -> None:
        provider = self._provider(bitable_tasks_table_id="tbl_tasks")
        provider.db.upsert_task(TaskRecord(
            guid="rec_x", title="Turret", status="pending", source="bitable",
        ))
        token_payload = {"code": 0, "msg": "success", "tenant_access_token": "t-token", "expire": 7200}
        with __import__("unittest.mock").mock.patch(
            "rmtask.api.bitable.delete_record",
            side_effect=[FeishuAPIError("missing scope", code=99991679), None],
        ) as del_mock, __import__("unittest.mock").mock.patch(
            "rmtask.api.auth.requests.post", return_value=fake_response(token_payload)
        ):
            provider.delete_task("rec_x", open_id="ou_me")
        self.assertEqual(del_mock.call_count, 2)
        self.assertEqual(del_mock.call_args_list[0].kwargs["token"], "u-token")
        self.assertEqual(del_mock.call_args_list[1].kwargs["token"], "t-token")

    def test_cancel_bitable_uses_availed_status(self) -> None:
        provider = self._provider(bitable_tasks_table_id="tbl_tasks")
        provider.db.upsert_task(TaskRecord(
            guid="rec_c", title="Turret", status="pending", source="bitable",
        ))
        record = {"record_id": "rec_c", "fields": {"任务状态（由技术组长验收）": "已放弃"}}
        with __import__("unittest.mock").mock.patch("rmtask.api.base.requests.request",
                                                   return_value=fake_response(ok({"record": record}))) as req:
            task = provider.cancel_task("rec_c", open_id="ou_me")
        self.assertEqual(task.status, "cancelled")
        self.assertEqual(req.call_args.kwargs["json"]["fields"], {"任务状态（由技术组长验收）": "已放弃"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
