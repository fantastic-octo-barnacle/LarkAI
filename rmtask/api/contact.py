"""contact-v3 wrappers: read user profile (including email) from the directory."""

from __future__ import annotations

from typing import Any

from .base import FeishuClient

USER_PATH = "/open-apis/contact/v3/users/{user_id}"


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
