from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from app.db.session import dispose_engine, init_db
from app.main import app
from app.scraping.fetcher import FetchError
from app.state import runtime

PRODUCT_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Test Product XYZ",
 "image":"/img/product.png",
 "offers":{"@type":"Offer","price":"123.45","priceCurrency":"PLN","availability":"https://schema.org/InStock"}}
</script>
</head><body><h1>ignored</h1></body></html>
"""


class FakeFetcher:

    def __init__(self) -> None:
        self.html_by_url: dict[str, str] = {}
        self.fail_urls: dict[str, str] = {}  
        self.feed_payload: bytes = b"<rss><channel></channel></rss>"
        self.calls: list[str] = []

    async def get_text(self, url: str) -> tuple[str, str, int]:
        self.calls.append(url)
        if url in self.fail_urls:
            raise FetchError(self.fail_urls[url], status=503)
        return self.html_by_url.get(url, PRODUCT_HTML), url, 200

    async def get_bytes(self, url: str) -> bytes:
        return self.feed_payload

    async def aclose(self) -> None:
        pass


@pytest.fixture
async def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    await dispose_engine()
    await init_db()
    yield
    await dispose_engine()
    get_settings.cache_clear()


@pytest.fixture
def fake_fetcher():
    fetcher = FakeFetcher()
    runtime.fetcher = fetcher
    runtime.adapters = []
    yield fetcher
    runtime.fetcher = None


@pytest.fixture
async def client(fake_fetcher, fresh_db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
