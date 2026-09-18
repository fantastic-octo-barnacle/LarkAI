"""Flask app factory."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from flask import Flask, g

from rmtask.config import Settings, env
from rmtask.notify.service import maybe_send_digest
from rmtask.providers import build_provider
from rmtask.storage.db import DB

_auto_started = False
_auto_lock = threading.Lock()


def _start_auto_collect(settings: Settings) -> None:
    """Background collection loop (single-process only; use cron in production)."""
    global _auto_started
    with _auto_lock:
        if _auto_started:
            return
        _auto_started = True

    def worker() -> None:
        from rmtask.collector.pipeline import collect_all
        from rmtask.storage.db import DB

        while True:
            time.sleep(settings.auto_collect_seconds)
            try:
                db = DB(settings.db_path)
                db.init()
                open_id = db.first_user_open_id()
                result = collect_all(db, build_provider(settings, db), open_id=open_id)
                print(
                    f"[auto-collect] tasks={len(result.tasks)} events={len(result.events)} "
                    f"warnings={len(result.warnings)}"
                )
                maybe_send_digest(db, settings, result)
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                print(f"[auto-collect] failed: {exc}")

    threading.Thread(target=worker, daemon=True, name="rm-auto-collect").start()


def create_app(settings: Settings | None = None) -> Flask:
    cfg = settings or env
    app = Flask(__name__)
    app.config["SETTINGS"] = cfg
    app.secret_key = cfg.secret_key or "dev-secret-change-me"
    app.config["JSON_AS_ASCII"] = False
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    from rmtask.web.access import configure_access

    configure_access(app)
    from rmtask.web.oidc import configure_oidc
    configure_oidc(app, cfg)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    from rmtask.web.routes import bp

    app.register_blueprint(bp)

    @app.template_filter("dt")
    def _dt_filter(value: str) -> str:
        if not value:
            return "—"
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value[:16]

    @app.before_request
    def _wire() -> None:
        db = DB(cfg.db_path)
        db.init()
        g.db = db
        g.settings = cfg
        g.provider = build_provider(cfg, db)

    from rmtask.web.feishu_connection import require_feishu
    app.before_request(require_feishu)

    if cfg.auto_collect_seconds > 0:
        _start_auto_collect(cfg)

    return app
