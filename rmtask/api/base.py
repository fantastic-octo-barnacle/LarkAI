"""Low-level HTTP client for the Feishu OpenAPI."""

from __future__ import annotations

import time
from typing import Any, Callable

import requests

from rmtask.errors import FeishuAPIError


class FeishuClient:
    """Bearer-token HTTP client. `token_provider` can be a callable returning
    the access token used when no explicit token is passed."""

    def __init__(
        self,
        base_url: str = "https://open.feishu.cn",
        *,
        token_provider: Callable[[], str] | None = None,
        timeout: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_provider = token_provider
        self.timeout = timeout

    def _token(self, token: str | None) -> str | None:
        if token:
            return token
        if self.token_provider:
            return self.token_provider()
        return None

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        auth = self._token(token)
        if auth:
            headers["Authorization"] = f"Bearer {auth}"
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = requests.request(method, url, headers=headers, params=params, json=json, timeout=self.timeout)
                break
            except requests.RequestException as exc:  # transient network blip
                last_exc = exc
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
        else:
            raise FeishuAPIError(
                f"Feishu network error ({type(last_exc).__name__}): {last_exc}"
            ) from last_exc
        try:
            payload = resp.json()
        except ValueError as exc:
            raise FeishuAPIError(
                f"{method} {path} returned non-JSON ({resp.status_code}): {resp.text[:200]}"
            ) from exc
        if payload.get("code") != 0:
            raise FeishuAPIError(
                payload.get("msg") or f"{method} {path} failed",
                code=payload.get("code"),
                data=payload,
            )
        return payload.get("data", payload)

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("DELETE", path, **kwargs)

    def list_all(self, path: str, *, list_key: str, token: str | None = None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Paged GET helper returning every item from a `data.*` list field."""
        items: list[dict[str, Any]] = []
        page_token = ""
        query = dict(params or {})
        query.setdefault("page_size", 50)
        while True:
            query["page_token"] = page_token
            data = self.get(path, token=token, params=query)
            items.extend(data.get(list_key) or [])
            page_token = data.get("page_token") or ""
            if not data.get("has_more") or not page_token:
                break
        return items
