"""Fetch all org users + team group members (incl. externals) and cache them.

Usage:
    python -m scripts.fetch_members

Requires directory/IM scopes (e.g. contact:contact:readonly_as_app or
contact:contact:access_as_app, and im:chat / im:chat:readonly for group
members); falls back from the user token to the tenant token.
"""

from __future__ import annotations

import json

from rmtask.collector.members import fetch_all_members
from rmtask.config import get_settings, load_env
from rmtask.providers import LiveProvider
from rmtask.storage.db import DB


def main() -> None:
    load_env()
    settings = get_settings()
    db = DB(settings.db_path)
    provider = LiveProvider(settings, db)
    admin = db.first_user_open_id()
    if not admin:
        raise SystemExit("No logged-in user in the local token store; login through the website first.")
    result = fetch_all_members(provider, db, open_id=admin)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    for warning in result["warnings"]:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()
