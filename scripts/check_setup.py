"""Validate the local configuration and print a launch checklist.

Usage:
    python -m scripts.check_setup
"""

from __future__ import annotations

from rmtask.config import load_env, get_settings
from rmtask.storage.db import DB


def main() -> None:
    load_env()
    s = get_settings()
    ok = True

    def flag(good: bool, label: str, fix: str = "", hard: bool = True) -> None:
        nonlocal ok
        if good:
            print(f"[OK ] {label}")
        elif hard:
            print(f"[!! ] {label} -> {fix}")
            ok = False
        else:
            print(f"[i  ] {label} -> {fix}")

    print(f"mode = {s.mode}")
    if s.mode == "live":
        flag(bool(s.app_id), "FEISHU_APP_ID is set", "copy it from open.feishu.cn/app -> 凭证与基础信息")
        flag(bool(s.app_secret), "FEISHU_APP_SECRET is set", "same page (kept out of git)")
        flag(bool(s.redirect_uri), "FEISHU_REDIRECT_URI is set",
             "use http://127.0.0.1:5000/oauth/callback locally and add it to 安全设置 -> 重定向 URL")
        flag(bool(s.bitable_app_token or s.wiki_node_token),
             "Bitable app_token / wiki token is set",
             "set FEISHU_BITABLE_APP_TOKEN (feishu.cn/base/<app_token>) or FEISHU_WIKI_NODE_TOKEN")
        flag(bool(s.bitable_submit_table_id), "FEISHU_BITABLE_SUBMIT_TABLE_ID is set",
             "tbl id of the 任务管理表 (needed to submit website tasks to Bitable)")
    flag(bool(s.secret_key) and s.secret_key != "change-me-in-production",
         "FLASK_SECRET_KEY is a real secret", "set a random value for production", hard=False)
    flag(bool(s.admin_open_ids), "FEISHU_ADMIN_OPEN_IDS are set",
         "empty is fine: the first user to log in becomes admin", hard=False)
    flag(s.email_configured, "SMTP email is configured",
         "set SMTP_HOST + NOTIFY_EMAIL_TO (empty = dry-run mode)", hard=False)
    flag(s.auto_collect_seconds > 0, "auto-collect is enabled",
         f"set RM_AUTO_COLLECT_SECONDS (current: {s.auto_collect_seconds})", hard=False)

    db = DB(s.db_path)
    db.init()
    users = db.list_users()
    with db.connect() as conn:
        token_rows = conn.execute("SELECT COUNT(*) FROM oauth_tokens").fetchone()[0]
    print(f"database = {s.db_path} (users={len(users)}, oauth_tokens={token_rows})")
    if s.mode == "live" and not token_rows:
        print("[i  ] no Feishu login yet -> open the website and click Login before Sync")
    print("LAUNCH READY: make run" if ok else "FIX THE ITEMS ABOVE, then: make run")


if __name__ == "__main__":
    main()
