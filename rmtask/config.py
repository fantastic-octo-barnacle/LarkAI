"""Environment-based configuration with a minimal .env loader."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: str | Path | None = None) -> None:
    """Populate os.environ from a .env file if the key is not already set."""
    env_file = Path(path) if path else ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value else default
    except (TypeError, ValueError):
        return default


def _list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item for item in value.replace(",", " ").split() if item]


@dataclass
class Settings:
    mode: str = "mock"
    app_id: str = ""
    app_secret: str = ""
    redirect_uri: str = ""
    scopes: list[str] = field(default_factory=list)
    base_url: str = "https://open.feishu.cn"
    accounts_url: str = "https://accounts.feishu.cn"

    chat_ids: list[str] = field(default_factory=list)
    calendar_id: str = ""
    bitable_app_token: str = ""
    wiki_node_token: str = ""
    bitable_submit_table_id: str = ""
    bitable_tasks_table_id: str = ""
    bitable_name_field: str = "任务名称"
    bitable_desc_field: str = "备注"
    bitable_type_field: str = "兵种类型"
    bitable_division_field: str = "研发组别"
    bitable_requirement_field: str = "任务需求（兵种组长填写）（务必详细！）"
    bitable_remark_field: str = "备注"
    bitable_ddl_field: str = "ddl"
    bitable_priority_field: str = "优先级"
    bitable_owner_field: str = "负责人"
    bitable_status_field: str = "任务状态（由技术组长验收）"
    bitable_default_status: str = "待执行"
    tenant_name: str = "RoboMaster Research Team"
    admin_open_ids: list[str] = field(default_factory=list)

    db_path: str = str(ROOT / "data" / "rmtask.db")
    mock_data_dir: str = str(ROOT / "data")
    secret_key: str = ""
    host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False
    auto_collect_seconds: int = 0

    email_from: str = "rmtasks@example.com"
    email_to: list[str] = field(default_factory=list)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    notify_on_task_change: bool = True

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.email_from and self.email_to)

    @property
    def bitable_write_configured(self) -> bool:
        return bool(self.bitable_submit_table_id or self.bitable_tasks_table_id)


def get_settings() -> Settings:
    return Settings(
        mode=os.environ.get("FEISHU_MODE", "mock").strip().lower(),
        app_id=os.environ.get("FEISHU_APP_ID", ""),
        app_secret=os.environ.get("FEISHU_APP_SECRET", ""),
        redirect_uri=os.environ.get("FEISHU_REDIRECT_URI", ""),
        scopes=_list(os.environ.get("FEISHU_SCOPES", "auth:user.id:read task:task:read offline_access")),
        base_url=os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/"),
        accounts_url=os.environ.get("FEISHU_ACCOUNTS_URL", "https://accounts.feishu.cn").rstrip("/"),
        chat_ids=_list(os.environ.get("FEISHU_CHAT_IDS", "")),
        calendar_id=os.environ.get("FEISHU_CALENDAR_ID", ""),
        bitable_app_token=os.environ.get("FEISHU_BITABLE_APP_TOKEN", ""),
        wiki_node_token=os.environ.get("FEISHU_WIKI_NODE_TOKEN", ""),
        bitable_submit_table_id=os.environ.get("FEISHU_BITABLE_SUBMIT_TABLE_ID", ""),
        bitable_tasks_table_id=os.environ.get("FEISHU_BITABLE_TASKS_TABLE_ID", ""),
        bitable_name_field=os.environ.get("FEISHU_BITABLE_NAME_FIELD", "任务名称"),
        bitable_desc_field=os.environ.get("FEISHU_BITABLE_DESC_FIELD", "备注"),
        bitable_type_field=os.environ.get("FEISHU_BITABLE_TYPE_FIELD", "兵种类型"),
        bitable_division_field=os.environ.get("FEISHU_BITABLE_DIVISION_FIELD", "研发组别"),
        bitable_requirement_field=os.environ.get(
            "FEISHU_BITABLE_REQUIREMENT_FIELD", "任务需求（兵种组长填写）（务必详细！）"),
        bitable_remark_field=os.environ.get("FEISHU_BITABLE_REMARK_FIELD", "备注"),
        bitable_ddl_field=os.environ.get("FEISHU_BITABLE_DDL_FIELD", "ddl"),
        bitable_priority_field=os.environ.get("FEISHU_BITABLE_PRIORITY_FIELD", "优先级"),
        bitable_owner_field=os.environ.get("FEISHU_BITABLE_OWNER_FIELD", "负责人"),
        bitable_status_field=os.environ.get("FEISHU_BITABLE_STATUS_FIELD", "任务状态（由技术组长验收）"),
        bitable_default_status=os.environ.get("FEISHU_BITABLE_DEFAULT_STATUS", "待执行"),
        tenant_name=os.environ.get("FEISHU_TENANT_NAME", "RoboMaster Research Team"),
        admin_open_ids=_list(os.environ.get("FEISHU_ADMIN_OPEN_IDS", "")),
        db_path=os.environ.get("RM_DB_PATH", str(ROOT / "data" / "rmtask.db")),
        mock_data_dir=os.environ.get("RM_MOCK_DATA_DIR", str(ROOT / "data")),
        secret_key=os.environ.get("FLASK_SECRET_KEY", ""),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=_int(os.environ.get("PORT"), 5000),
    debug=_bool(os.environ.get("DEBUG"), False),
    auto_collect_seconds=_int(os.environ.get("RM_AUTO_COLLECT_SECONDS"), 0),
        email_from=os.environ.get("NOTIFY_EMAIL_FROM", "rmtasks@example.com"),
        email_to=_list(os.environ.get("NOTIFY_EMAIL_TO", "")),
        smtp_host=os.environ.get("SMTP_HOST", ""),
        smtp_port=_int(os.environ.get("SMTP_PORT"), 587),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        smtp_starttls=_bool(os.environ.get("SMTP_STARTTLS"), True),
        smtp_ssl=_bool(os.environ.get("SMTP_SSL"), False),
        notify_on_task_change=_bool(os.environ.get("NOTIFY_ON_TASK_CHANGE"), True),
    )


load_env()
env = get_settings()
