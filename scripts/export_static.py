"""Render the site to a static snapshot in ./site (for GitHub Pages).

Usage:  python -m scripts.export_static [--out site]
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from rmtask.config import ROOT, load_env
from rmtask.collector.pipeline import collect_all
from rmtask.providers import build_provider
from rmtask.storage.db import DB
from flask import g, render_template

from rmtask.web.app import create_app

load_env()

# Routes rendered by the snapshot; forms/buttons stay visible but are inert in
# a pure-static deploy (interactive actions require the Flask backend).
PAGES = {
    "/": "index.html",
    "/timeline": "timeline.html",
    "/tasks": "tasks.html",
    "/workload": "workload.html",
    "/notifications": "notifications.html",
    "/settings": "settings.html",
}

API_PAGES = {
    "/api/stats.json": "api/stats.json",
    "/api/timeline.json": "api/timeline.json",
    "/api/team.json": "api/team.json",
    "/api/workload.json": "api/workload.json",
}


def _fix_links(html: str) -> str:
    """Make root-absolute links relative so the snapshot works under a subpath."""
    html = re.sub(r'(href|src)="/', r'\1="./', html)
    html = re.sub(r'(href|src)="/static/', r'\1="./static/', html)
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a static snapshot of the site")
    parser.add_argument("--out", default=str(ROOT / "site"))
    parser.add_argument("--no-collect", action="store_true", help="skip the collection step")
    args = parser.parse_args()

    from rmtask.config import env

    out = Path(args.out)
    db = DB(env.db_path)
    db.init()
    if not args.no_collect:
        provider = build_provider(env, db)
        result = collect_all(db, provider, open_id=db.first_user_open_id())
        print(f"collected {len(result.tasks)} tasks, {len(result.events)} events")

    app = create_app(env)
    app.config["TESTING"] = True
    client = app.test_client()

    (out / "static").mkdir(parents=True, exist_ok=True)
    (out / "api").mkdir(parents=True, exist_ok=True)
    for route, filename in PAGES.items():
        resp = client.get(route)
        if resp.status_code != 200:
            raise SystemExit(f"export failed: {route} -> {resp.status_code}")
        (out / filename).write_text(_fix_links(resp.get_data(as_text=True)), encoding="utf-8")
        print(f"wrote {out / filename}")
    for route, filename in API_PAGES.items():
        resp = client.get(route)
        (out / filename).write_text(resp.get_data(as_text=True), encoding="utf-8")
        print(f"wrote {out / filename}")
    with app.test_request_context("/login"):
        g.db = db
        g.settings = env
        g.provider = build_provider(env, db)
        (out / "login.html").write_text(_fix_links(render_template("login.html")), encoding="utf-8")
        print(f"wrote {out / 'login.html'}")
    shutil.copy2(ROOT / "rmtask" / "web" / "static" / "style.css", out / "static" / "style.css")
    shutil.copy2(ROOT / "rmtask" / "web" / "static" / "app.js", out / "static" / "app.js")
    print("done")


if __name__ == "__main__":
    main()
