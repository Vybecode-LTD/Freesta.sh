"""One shared async HTTP client: identifiable UA, retries with backoff, small in-memory TTL cache."""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections import OrderedDict
from typing import Any

import httpx

from freestash.config import Settings, get_settings

RETRY_STATUS = {429, 500, 502, 503, 504}


class ProviderHTTPError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = "") -> None:
        self.status = status
        self.url = url
        super().__init__(f"HTTP {status} from {url.split('?')[0]}" + (f": {body[:160]}" if body else ""))


class TTLCache:
    def __init__(self, max_items: int = 512) -> None:
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max = max_items

    def get(self, key: str) -> Any | None:
        hit = self._data.get(key)
        if not hit:
            return None
        expires, value = hit
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        self._data[key] = (time.monotonic() + ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)


class HttpClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = TTLCache()
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self.settings.full_user_agent, "Accept": "application/json"},
            timeout=httpx.Timeout(self.settings.http_timeout, connect=10.0),
            follow_redirects=True,
            transport=transport,
        )

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def raw(self) -> httpx.AsyncClient:
        return self._client

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
        *,
        cache_ttl: float | None = None,
        method: str = "GET",
        data: dict[str, Any] | None = None,
    ) -> Any:
        ttl = self.settings.cache_ttl_seconds if cache_ttl is None else cache_ttl
        key = json.dumps([method, url, params, sorted((headers or {}).items())], default=str)
        if method == "GET" and ttl > 0 and (hit := self.cache.get(key)) is not None:
            return hit

        attempts = self.settings.http_retries + 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = await self._client.request(method, url, params=params, headers=headers, data=data)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                await self._sleep(attempt, None)
                continue
            if resp.status_code in RETRY_STATUS and attempt < attempts - 1:
                await self._sleep(attempt, resp.headers.get("Retry-After"))
                continue
            if resp.status_code >= 400:
                raise ProviderHTTPError(resp.status_code, str(resp.url), resp.text)
            if not resp.content.strip():  # Openverse occasionally returns an empty 200
                last_exc = ProviderHTTPError(resp.status_code, str(resp.url), "empty body")
                await self._sleep(attempt, None)
                continue
            payload = resp.json()
            if method == "GET" and ttl > 0:
                self.cache.set(key, payload, ttl)
            return payload
        raise last_exc or RuntimeError(f"request failed: {url}")

    @staticmethod
    async def _sleep(attempt: int, retry_after: str | None) -> None:
        if retry_after and retry_after.isdigit():
            delay = min(float(retry_after), 8.0)
        else:
            delay = min(0.6 * (2**attempt) + random.uniform(0, 0.3), 8.0)
        await asyncio.sleep(delay)
