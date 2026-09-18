"""Shared exception types."""


class RmTaskError(Exception):
    """Base error for the whole project."""


class ConfigError(RmTaskError):
    """Missing or invalid configuration."""


class FeishuAPIError(RmTaskError):
    """A Feishu OpenAPI call failed."""

    def __init__(self, message: str, code: int | None = None, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.data = data or {}


class AuthError(RmTaskError):
    """Authentication / token refresh failed."""


class ProviderError(RmTaskError):
    """A provider (live or mock) could not complete the operation."""
