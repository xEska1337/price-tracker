from __future__ import annotations

import asyncio
import time

import httpx

from app.config import Settings
from app.scraping.normalize import domain_bucket

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None, final_url: str | None = None):
        super().__init__(message)
        self.status = status
        self.final_url = final_url


class Fetcher:

    def __init__(self, settings: Settings):
        self._min_gap = settings.scrape_min_gap_per_domain
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(settings.http_timeout, connect=10.0),
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.7,en;q=0.6",
            },
        )
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_hit: dict[str, float] = {}

    async def _wait_turn(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            wait = self._min_gap - (now - self._last_hit.get(host, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_hit[host] = time.monotonic()

    async def get_text(self, url: str) -> tuple[str, str, int]:
        host = domain_bucket(url)
        last_exc: Exception | None = None
        for attempt in range(2):
            await self._wait_turn(host)
            try:
                resp = await self._client.get(url)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(2.0)
                    continue
                raise FetchError(f"network error: {exc.__class__.__name__}: {exc}") from exc
            if resp.status_code in _RETRYABLE_STATUSES and attempt == 0:
                await asyncio.sleep(3.0)
                continue
            if resp.status_code >= 400:
                raise FetchError(
                    f"HTTP {resp.status_code}", status=resp.status_code, final_url=str(resp.url)
                )
            return resp.text, str(resp.url), resp.status_code
        raise FetchError(f"failed after retries: {last_exc}")

    async def get_bytes(self, url: str) -> bytes:
        host = domain_bucket(url)
        await self._wait_turn(host)
        resp = await self._client.get(url)
        if resp.status_code >= 400:
            raise FetchError(f"HTTP {resp.status_code}", status=resp.status_code, final_url=str(resp.url))
        return resp.content

    async def aclose(self) -> None:
        await self._client.aclose()
