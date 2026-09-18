"""Fetch the full member directory (org users + team group members) and cache it."""

from __future__ import annotations

from typing import Any, Callable

from rmtask.api import contact as contact_api
from rmtask.api import im as im_api
from rmtask.storage.models import UserRecord


def _tokens(provider: Any, open_id: str) -> list[tuple[str, str | None]]:
    """Token candidates to try in order: user token, tenant token, app default."""
    user_token = None
    if open_id:
        try:
            user_token = provider._user_token(open_id)
        except Exception:  # noqa: BLE001 - fall through to tenant/app token
            user_token = None
    tenant_token = None
    try:
        tenant_token = provider.auth.tenant_access_token()
    except Exception:  # noqa: BLE001 - client may still provide its default token
        tenant_token = None
    return [("user", user_token), ("tenant", tenant_token), ("app", None)]


def _call_with_tokens(
    fn: Callable[[str | None], list[dict[str, Any]]],
    tokens: list[tuple[str, str | None]],
    warnings: list[str],
    label: str,
) -> list[dict[str, Any]]:
    for name, token in tokens:
        if name != "app" and not token:
            continue
        try:
            return fn(token)
        except Exception as exc:  # noqa: BLE001 - try the next token/path
            warnings.append(f"{label} ({name}): {str(exc)[:160]}")
    return []


def _user_records(users: list[dict[str, Any]]) -> list[UserRecord]:
    out = []
    for u in users:
        oid = u.get("open_id") or u.get("member_id") or u.get("user_id") or ""
        if not oid:
            continue
        oid = str(oid)
        name = u.get("name") or u.get("en_name") or u.get("nickname") or oid
        avatar_info = u.get("avatar") or {}
        avatar = avatar_info.get("avatar_url") if isinstance(avatar_info, dict) else ""
        out.append(UserRecord(
            open_id=oid,
            name=str(name),
            email=str(u.get("email") or u.get("enterprise_email") or ""),
            avatar_url=str(avatar or ""),
        ))
    return out


def _is_named(user: UserRecord) -> bool:
    return bool(user.name) and user.name != user.open_id


def _placeholder_name(oid: str) -> str:
    return f"用户{oid[-6:]}"


def fetch_all_members(provider: Any, db: Any, open_id: str = "") -> dict[str, Any]:
    """Fetch every reachable member (directory + group chats, incl. externals)
    and upsert them into the local users table. Returns a summary dict."""
    warnings: list[str] = []
    tokens = _tokens(provider, open_id)

    org_users = _call_with_tokens(
        lambda token: contact_api.list_org_users(provider.client, token=token),
        tokens, warnings, "org users",
    )
    chats = _call_with_tokens(
        lambda token: im_api.list_chats(provider.client, token=token),
        tokens, warnings, "group chats",
    )

    chat_members: list[dict[str, Any]] = []
    seen_chats: set[str] = set()
    for chat in chats:
        chat_id = chat.get("chat_id") or chat.get("id") or ""
        if not chat_id or chat_id in seen_chats:
            continue
        seen_chats.add(chat_id)
        chat_members.extend(_call_with_tokens(
            lambda token, cid=chat_id: im_api.list_chat_members(provider.client, cid, token=token),
            tokens, warnings, f"chat {chat_id}",
        ))

    org_records = _user_records(org_users)
    chat_records = _user_records(chat_members)
    chat_by_id = {u.open_id: u for u in chat_records}
    for i, rec in enumerate(org_records):
        known = chat_by_id.get(rec.open_id)
        if known and not _is_named(rec):
            org_records[i] = UserRecord(
                open_id=rec.open_id, name=known.name or rec.name,
                email=rec.email or known.email, avatar_url=rec.avatar_url or known.avatar_url,
                is_admin=rec.is_admin,
            )
        elif not _is_named(rec):
            org_records[i] = UserRecord(
                open_id=rec.open_id, name=_placeholder_name(rec.open_id),
                email=rec.email, avatar_url=rec.avatar_url, is_admin=rec.is_admin,
            )
    merged: dict[str, UserRecord] = {}
    for u in org_records:
        merged[u.open_id] = u
    for u in chat_records:
        cur = merged.get(u.open_id)
        if cur is None or (_is_named(u) and not _is_named(cur)):
            merged[u.open_id] = u

    admin_open_id = open_id or db.first_user_open_id()
    for u in merged.values():
        u.is_admin = u.open_id == admin_open_id
        db.upsert_user(u)
    return {
        "users": len(merged),
        "org": len(org_records),
        "chat_members": len(chat_records),
        "warnings": warnings,
    }
