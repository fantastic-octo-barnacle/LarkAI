"""Thin wrappers around the Feishu OpenAPI (server side)."""

from .base import FeishuClient
from .auth import AuthManager

__all__ = ["FeishuClient", "AuthManager"]
