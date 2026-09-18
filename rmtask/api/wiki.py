"""wiki-v2 wrappers: resolve a wiki node token to its underlying object token."""

from __future__ import annotations

from typing import Any

from .base import FeishuClient

GET_NODE_PATH = "/open-apis/wiki/v2/spaces/get_node"


def get_node(client: FeishuClient, node_token: str, *, token: str | None = None) -> dict[str, Any]:
    """Resolve a wiki node (token from feishu.cn/wiki/<token>...).

    Returns the node dict; for a Bitable node this carries `obj_type="bitable"`
    and the base's `obj_token` (the app_token used by bitable/v1/apps/<app_token>).
    """
    data = client.get(GET_NODE_PATH, params={"token": node_token}, token=token)
    return data.get("node") or {}
