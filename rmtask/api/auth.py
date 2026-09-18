"""Feishu authentication: tenant token, OAuth v3 login, refresh, user info."""

from __future__ import annotations

import time
from urllib.parse import urlencode

import requests

from rmtask.config import Settings
from rmtask.errors import AuthError, FeishuAPIError


class AuthManager:
    def __init__(self, settings: Settings, tenant_token_store: dict | None = None) -> None:
        self.settings = settings
        self._tenant_cache = tenant_token_store if tenant_token_store is not None else {}

    # -- authorize page ----------------------------------------------------
    def build_authorize_url(self, state: str, scope: str | None = None) -> str:
        params = {
            "client_id": self.settings.app_id,
            "response_type": "code",
            "redirect_uri": self.settings.redirect_uri,
            "state": state,
        }
        scopes = scope if scope is not None else " ".join(self.settings.scopes)
        if scopes:
            params["scope"] = scopes
        return f"{self.settings.accounts_url}/open-apis/authen/v1/authorize?{urlencode(params)}"

    # -- tokens ------------------------------------------------------------
    def _post_token(self, data: dict[str, str]) -> dict:
        resp = requests.post(
            f"{self.settings.accounts_url}/oauth/v3/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AuthError(f"token endpoint returned non-JSON: {resp.text[:200]}") from exc
        if payload.get("code") != 0 or "access_token" not in payload:
            raise AuthError(payload.get("msg") or f"token error: {payload}")
        return payload

    def exchange_code(self, code: str) -> dict:
        """Exchange an authorization code for a user_access_token."""
        return self._post_token(
            {
                "grant_type": "authorization_code",
                "client_id": self.settings.app_id,
                "client_secret": self.settings.app_secret,
                "code": code,
                "redirect_uri": self.settings.redirect_uri,
            }
        )

    def refresh_user_token(self, refresh_token: str) -> dict:
        return self._post_token(
            {
                "grant_type": "refresh_token",
                "client_id": self.settings.app_id,
                "client_secret": self.settings.app_secret,
                "refresh_token": refresh_token,
            }
        )

    def user_info(self, access_token: str) -> dict:
        resp = requests.get(
            f"{self.settings.base_url}/open-apis/authen/v1/user_info",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AuthError(f"user_info returned non-JSON: {resp.text[:200]}") from exc
        if payload.get("code") != 0:
            raise FeishuAPIError(payload.get("msg") or "user_info failed", code=payload.get("code"))
        return payload.get("data", payload)

    def tenant_access_token(self) -> str:
        """App-identity token, cached until ~60s before expiry."""
        cached = self._tenant_cache.get("tenant")
        if cached and cached["expires_at"] > time.time():
            return cached["token"]
        resp = requests.post(
            f"{self.settings.base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.settings.app_id, "app_secret": self.settings.app_secret},
            timeout=15,
        )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AuthError(f"tenant token returned non-JSON: {resp.text[:200]}") from exc
        if payload.get("code") != 0 or not payload.get("tenant_access_token"):
            raise AuthError(payload.get("msg") or f"tenant token failed: {payload}")
        self._tenant_cache["tenant"] = {
            "token": payload["tenant_access_token"],
            "expires_at": time.time() + int(payload.get("expire", 7200)) - 60,
        }
        return payload["tenant_access_token"]
