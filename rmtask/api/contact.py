"""contact-v3 wrappers: read user profiles (and the full org directory)."""

from __future__ import annotations

from typing import Any

from .base import FeishuClient

USER_PATH = "/open-apis/contact/v3/users/{user_id}"
USERS_PATH = "/open-apis/contact/v3/users"
DEPARTMENTS_PATH = "/open-apis/contact/v3/departments"
FIND_BY_DEPARTMENT_PATH = "/open-apis/contact/v3/users/find_by_department"


def get_user(
    client: FeishuClient,
    user_id: str,
    *,
    user_id_type: str = "open_id",
    token: str | None = None,
) -> dict[str, Any]:
    """Fetch one user by open_id/union_id/user_id.

    Requires the directory scope (e.g. contact:contact.base:readonly); the
    `email` / `enterprise_email` fields are populated when the caller also
    holds the email scope (e.g. contact:user.email:readonly).
    """
    data = client.get(USER_PATH.format(user_id=user_id), params={"user_id_type": user_id_type}, token=token)
    return data.get("user") or {}


def list_users(
    client: FeishuClient,
    *,
    department_id: str = "",
    token: str | None = None,
) -> list[dict[str, Any]]:
    """List users in the visible directory scope (legacy endpoint).

    Without `department_id` only independent users are returned; with the root
    id (``0``) the whole org is returned when the full-directory permission
    is granted. Raise (permission code) so callers can fall back to the
    department walk in ``list_org_users``.
    """
    params: dict[str, Any] = {"user_id_type": "open_id", "department_id_type": "open_department_id"}
    if department_id:
        params["department_id"] = department_id
    return client.list_all(USERS_PATH, list_key="items", token=token, params=params)


def list_departments(
    client: FeishuClient,
    *,
    parent_department_id: str = "0",
    token: str | None = None,
) -> list[dict[str, Any]]:
    """List child departments below ``parent_department_id`` (root is ``0``)."""
    params: dict[str, Any] = {
        "parent_department_id": parent_department_id,
        "department_id_type": "open_department_id",
    }
    return client.list_all(DEPARTMENTS_PATH, list_key="items", token=token, params=params)


def list_department_users(
    client: FeishuClient,
    department_id: str,
    *,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """List the direct members of one department (root is ``0``)."""
    params: dict[str, Any] = {
        "department_id": department_id,
        "department_id_type": "open_department_id",
        "user_id_type": "open_id",
    }
    return client.list_all(FIND_BY_DEPARTMENT_PATH, list_key="items", token=token, params=params)


def list_org_users(client: FeishuClient, *, token: str | None = None) -> list[dict[str, Any]]:
    """Fetch every visible directory user: try the whole org in one call, then
    walk the department tree (root -> children) and list each department's
    direct members, de-duplicating by open_id."""
    users: dict[str, dict[str, Any]] = {}

    def add(items: list[dict[str, Any]]) -> None:
        for u in items:
            key = u.get("open_id") or u.get("user_id") or ""
            if key:
                users.setdefault(key, u)

    # Independent users in the visible scope (not children of a known dept).
    try:
        add(list_users(client, token=token))
    except Exception:  # noqa: BLE001 - best effort; department walk below
        pass

    seen_depts: set[str] = set()
    queue = ["0"]
    while queue:
        parent = queue.pop(0)
        if parent in seen_depts:
            continue
        seen_depts.add(parent)
        try:
            depts = list_departments(client, parent_department_id=parent, token=token)
        except Exception:  # noqa: BLE001 - skip dept without permission
            continue
        for dept in depts:
            dept_id = dept.get("open_department_id") or dept.get("department_id") or ""
            if dept_id:
                queue.append(dept_id)
        # Direct members of the current node (root=0, each dept, and leaves).
        try:
            add(list_department_users(client, parent, token=token))
        except Exception:  # noqa: BLE001 - skip dept without permission
            pass
    return list(users.values())
