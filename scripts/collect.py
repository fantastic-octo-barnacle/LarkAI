"""Collect from Feishu (or mock) and print the digest.

Usage:
    python -m scripts.collect [--open-id ou_xxx] [--force-reinit]
"""

from __future__ import annotations

import argparse
import json

from rmtask.config import load_env
from rmtask.collector.pipeline import collect_all
from rmtask.notify import Emailer, notify_important_digest
from rmtask.providers import build_provider
from rmtask.storage.db import DB

load_env()


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Feishu info into the local store")
    parser.add_argument("--open-id", default="", help="user open_id to act as (live mode)")
    parser.add_argument("--notify", action="store_true",
                        help="email a digest of important timeline items after collecting")
    args = parser.parse_args()

    from rmtask.config import env

    db = DB(env.db_path)
    db.init()
    provider = build_provider(env, db)
    open_id = args.open_id or db.first_user_open_id()
    result = collect_all(db, provider, open_id=open_id)
    print(f"mode={env.mode} tasks={len(result.tasks)} events={len(result.events)}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    if args.notify:
        notify_important_digest(db, Emailer(env), env, items=result.digest["latest_important"])
        print("important digest queued (status in DB notifications)")
    print(json.dumps(result.digest, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
