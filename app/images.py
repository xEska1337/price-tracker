from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import socket
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

ALLOWED_PORTS = {80, 443}
MAX_REDIRECTS = 3
_CHUNK = 64 * 1024


class ImageProxyError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


class ImageProxy:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        resolver=None,
    ):
        self._settings = settings
        self._ttl = settings.image_cache_ttl_days * 86400
        self._max_bytes = settings.image_max_bytes
        self._dir = Path(settings.image_cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_cache_bytes = settings.image_cache_max_mb * 1024 * 1024
        self._client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(settings.http_timeout, connect=8.0),
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8",
            },
        )
        self._resolver = resolver or self._system_resolver
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    async def _system_resolver(host: str) -> list[str]:
        def _resolve() -> list[str]:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            return [info[4][0] for info in infos]

        return await asyncio.to_thread(_resolve)

    def _validate_url(self, raw_url: str) -> str:
        parts = urlsplit(raw_url)
        if parts.scheme not in ("http", "https"):
            raise ImageProxyError(400, "Only http and https image URLs are allowed")
        if not parts.hostname:
            raise ImageProxyError(400, "Invalid image URL")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if port not in ALLOWED_PORTS:
            raise ImageProxyError(400, "Image URL port is not allowed")
        return raw_url

    async def _assert_public(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        if host in ("localhost",) or host.endswith(".localhost"):
            raise ImageProxyError(400, "Local addresses are not allowed")
        try:
            addresses = await self._resolver(host)
        except OSError as exc:
            raise ImageProxyError(502, "Could not resolve the image host") from exc
        if not addresses:
            raise ImageProxyError(502, "Could not resolve the image host")
        if any(not _is_public_ip(address) for address in addresses):
            raise ImageProxyError(400, "Private or local addresses are not allowed")

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self._dir / f"{key}.bin", self._dir / f"{key}.json"

    def _read_cache(self, url: str) -> tuple[bytes, str, str] | None:
        data_path, meta_path = self._cache_paths(url)
        if not data_path.is_file() or not meta_path.is_file():
            return None
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - meta.get("saved_at", 0) > self._ttl:
            return None
        try:
            data = data_path.read_bytes()
        except OSError:
            return None
        return data, meta.get("content_type", "application/octet-stream"), meta.get("etag", "")

    def _write_cache(self, url: str, data: bytes, content_type: str, etag: str) -> None:
        data_path, meta_path = self._cache_paths(url)
        try:
            data_path.write_bytes(data)
            meta_path.write_text(
                json.dumps(
                    {
                        "url": url,
                        "content_type": content_type,
                        "etag": etag,
                        "saved_at": time.time(),
                        "size": len(data),
                    }
                ),
                "utf-8",
            )
            self._prune()
        except OSError:
            logger.debug("could not cache image %s", url)

    def _prune(self) -> None:
        try:
            files = sorted(
                (p for p in self._dir.iterdir() if p.is_file()),
                key=lambda p: p.stat().st_mtime,
            )
        except OSError:
            return
        total = sum(p.stat().st_size for p in files)
        while total > self._max_cache_bytes and files:
            oldest = files.pop(0)
            try:
                total -= oldest.stat().st_size
                oldest.unlink()
            except OSError:
                break

    async def _download(self, url: str) -> tuple[bytes, str, str]:
        current = self._validate_url(url)
        for _hop in range(MAX_REDIRECTS + 1):
            await self._assert_public(current)
            try:
                async with self._client.stream(
                    "GET", current, headers={"Referer": ""}
                ) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise ImageProxyError(502, "Redirect without a location")
                        current = self._validate_url(urljoin(current, location))
                        continue
                    if response.status_code >= 400:
                        raise ImageProxyError(502, f"Image host returned HTTP {response.status_code}")
                    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
                    if not content_type.startswith("image/"):
                        raise ImageProxyError(502, "The URL did not return an image")
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > self._max_bytes:
                        raise ImageProxyError(502, "Image is too large")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes(_CHUNK):
                        size += len(chunk)
                        if size > self._max_bytes:
                            raise ImageProxyError(502, "Image is too large")
                        chunks.append(chunk)
                    data = b"".join(chunks)
            except httpx.HTTPError as exc:
                raise ImageProxyError(502, f"Could not fetch the image: {exc.__class__.__name__}") from exc
            etag = hashlib.sha256(data).hexdigest()[:32]
            return data, content_type, etag
        raise ImageProxyError(502, "Too many redirects")

    async def fetch(self, url: str) -> tuple[bytes, str, str]:
        cached = self._read_cache(url)
        if cached is not None:
            return cached
        lock = self._locks.setdefault(url, asyncio.Lock())
        async with lock:
            cached = self._read_cache(url)  
            if cached is not None:
                return cached
            data, content_type, etag = await self._download(url)
            self._write_cache(url, data, content_type, etag)
            return data, content_type, etag

    async def aclose(self) -> None:
        await self._client.aclose()
