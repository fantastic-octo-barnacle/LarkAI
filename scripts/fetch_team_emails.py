"""Fetch member emails from the Feishu contact directory and cache them locally.

Usage:
    python -m scripts.fetch_team_emails [--limit 8]

Requires the contact scope (contact:contact.base:readonly, optionally
contact:user.email:readonly) to be granted to the app and, for user-token
reads, granted during re-login. Falls back to the app (tenant) token when the
user token lacks the scope.
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict

from rmtask.api import bitable as bitable_api
from rmtask.api import contact as contact_api
from rmtask.config import load_env, get_settings
from rmtask.providers import LiveProvider
from rmtask.storage.db import DB
from rmtask.storage.models import UserRecord


def collect_persons(provider: LiveProvider, settings, open_id: str) -> dict[str, str]:
    """open_id -> display name, gathered from Bitable 负责人 fields."""
    persons: OrderedDict[str, str] = OrderedDict()
    try:
        records = bitable_api.search_records(
            provider.client, provider.resolve_bitable_app_token(open_id),
            settings.bitable_submit_table_id, token=provider._user_token(open_id),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Bitable lookup failed: {exc}")
        records = []
    for r in records:
        for p in (r.get("fields") or {}).get("负责人", []) or []:
            if isinstance(p, dict) and p.get("id"):
                persons[p["id"]] = p.get("name") or p.get("en_name") or p.get("id")
    return dict(persons)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    load_env()
    settings = get_settings()
    db = DB(settings.db_path)
    provider = LiveProvider(settings, db)
    admin = db.first_user_open_id()
    if not admin:
        raise SystemExit("No logged-in user in the local token store; login through the website first.")

    persons = collect_persons(provider, settings, admin)
    if admin not in persons:
        persons[admin] = "Me"
    user_token = provider._user_token(admin)
    tenant_token = None
    try:
        tenant_token = provider.auth.tenant_access_token()
    except Exception as exc:  # noqa: BLE001
        print(f"tenant token unavailable: {exc}")

    samples = []
    for oid, name in list(persons.items())[: args.limit]:
        info = None
        for label, token in (("user", user_token), ("tenant", tenant_token)):
            if not token:
                continue
            try:
                info = contact_api.get_user(provider.client, oid, token=token)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"[{label}] {name}: {str(exc)[:120]}")
        if info is None:
            continue
        email = info.get("email") or info.get("enterprise_email") or ""
        samples.append({"name": info.get("name") or name, "open_id": oid,
                        "email": email, "enterprise_email": info.get("enterprise_email") or ""})
        if email:
            db.upsert_user(UserRecord(open_id=oid, name=info.get("name") or name, email=email,
                                      avatar_url=info.get("avatar_url") or "", is_admin=oid == admin))

    print(json.dumps(samples, ensure_ascii=False, indent=2))
    print(f"\nCached {sum(1 for s in samples if s['email'])} email(s) into users.")


if __name__ == "__main__":
    main()
