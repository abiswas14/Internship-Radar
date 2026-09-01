from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx


class PermanentHttpError(RuntimeError):
    pass


@dataclass(slots=True)
class CachedResponse:
    content: bytes
    etag: str | None
    last_modified: str | None
    status_code: int
    url: str

    def json(self) -> object:
        import json

        return json.loads(self.content)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 30,
        max_retries: int = 3,
        per_domain_concurrency: int = 2,
    ) -> None:
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(timeout_seconds),
            limits=limits,
            follow_redirects=True,
        )
        self._max_retries = max_retries
        self._per_domain_concurrency = per_domain_concurrency
        self._domain_locks: dict[str, asyncio.Semaphore] = {}
        self._cache: dict[str, CachedResponse] = {}

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _lock(self, url: str) -> asyncio.Semaphore:
        domain = urlsplit(url).netloc.casefold()
        return self._domain_locks.setdefault(
            domain, asyncio.Semaphore(self._per_domain_concurrency)
        )

    async def get(self, url: str, *, params: dict[str, object] | None = None) -> CachedResponse:
        request = self._client.build_request("GET", url, params=params)
        cache_key = str(request.url)
        cached = self._cache.get(cache_key)
        if cached:
            if cached.etag:
                request.headers["If-None-Match"] = cached.etag
            if cached.last_modified:
                request.headers["If-Modified-Since"] = cached.last_modified

        async with self._lock(url):
            for attempt in range(self._max_retries + 1):
                try:
                    response = await self._client.send(request)
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt >= self._max_retries:
                        raise RuntimeError(f"request failed after retries: {request.url}") from exc
                    await asyncio.sleep((2**attempt) + random.random())
                    continue

                if response.status_code == 304 and cached:
                    return cached
                if response.status_code in {408, 425, 429} or 500 <= response.status_code < 600:
                    if attempt >= self._max_retries:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    delay = (2**attempt) + random.random()
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            try:
                                when = parsedate_to_datetime(retry_after)
                                delay = max(delay, when.timestamp() - __import__("time").time())
                            except (TypeError, ValueError):
                                pass
                    await asyncio.sleep(min(delay, 60))
                    continue
                if 400 <= response.status_code < 500:
                    raise PermanentHttpError(f"HTTP {response.status_code} for {request.url}")
                response.raise_for_status()
                result = CachedResponse(
                    content=response.content,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                    status_code=response.status_code,
                    url=str(response.url),
                )
                self._cache[cache_key] = result
                return result
        raise AssertionError("unreachable")
