from app.config import Settings
from app.db.models import Product, utcnow
from app.db.session import get_session_factory
from app.scraping.browser import BrowserUnavailable
from app.scraping.service import scrape_product

PLAIN_PAGE = "<html><body><h1>No structured data</h1></body></html>"

RENDERED_PAGE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Rendered Product",
 "image":"https://cdn.example/r.png",
 "offers":{"@type":"Offer","price":"249.99","priceCurrency":"PLN",
           "availability":"https://schema.org/InStock"}}
</script></head><body></body></html>
"""


class FakeFetcher:
    def __init__(self, html: str):
        self.html = html

    async def get_text(self, url):
        return self.html, url, 200

    async def get_bytes(self, url):
        return b""


class FakeRenderer:
    def __init__(self, html: str | None = RENDERED_PAGE, available: bool = True):
        self.html = html
        self.calls = 0
        self._available = available

    async def is_available(self):
        return self._available

    @property
    def unavailable_reason(self):
        return None if self._available else "fake unavailable"

    async def render(self, url):
        self.calls += 1
        if self.html is None:
            raise BrowserUnavailable("cannot render")
        return self.html, url


async def _make_product(session, url="https://shop.example/p/1"):
    product = Product(
        url=url, url_canonical=url, domain="shop.example", interval="24h",
        status="active", next_check_at=utcnow(),
    )
    session.add(product)
    await session.commit()
    return product


async def test_browser_fallback_used_when_plain_extraction_fails(fresh_db):
    settings = Settings()
    renderer = FakeRenderer()
    async with get_session_factory()() as session:
        product = await _make_product(session)
        result = await scrape_product(
            session, product, FakeFetcher(PLAIN_PAGE), settings, [], renderer
        )
    assert result.ok is True
    assert result.data.price == 249.99
    assert result.extractor is not None and "browser" in result.extractor
    assert renderer.calls == 1
    assert product.last_price == 249.99


async def test_browser_not_used_when_plain_extraction_succeeds(fresh_db):
    settings = Settings()
    renderer = FakeRenderer()
    async with get_session_factory()() as session:
        product = await _make_product(session)
        result = await scrape_product(
            session, product, FakeFetcher(RENDERED_PAGE), settings, [], renderer
        )
    assert result.ok is True
    assert renderer.calls == 0
    assert "browser" not in (result.extractor or "")


async def test_browser_disabled_by_setting(fresh_db):
    settings = Settings(playwright_enabled=False)
    renderer = FakeRenderer()
    async with get_session_factory()() as session:
        product = await _make_product(session)
        result = await scrape_product(
            session, product, FakeFetcher(PLAIN_PAGE), settings, [], renderer
        )
    assert result.ok is False
    assert renderer.calls == 0
    assert result.error and "No price found" in result.error


async def test_browser_unavailable_is_graceful(fresh_db):
    settings = Settings()
    renderer = FakeRenderer(available=False)
    async with get_session_factory()() as session:
        product = await _make_product(session)
        result = await scrape_product(
            session, product, FakeFetcher(PLAIN_PAGE), settings, [], renderer
        )
    assert result.ok is False
    assert renderer.calls == 0


async def test_browser_render_failure_is_graceful(fresh_db):
    settings = Settings()
    renderer = FakeRenderer(html=None)
    async with get_session_factory()() as session:
        product = await _make_product(session)
        result = await scrape_product(
            session, product, FakeFetcher(PLAIN_PAGE), settings, [], renderer
        )
    assert result.ok is False
    assert result.error and "No price found" in result.error


async def test_no_renderer_configured(fresh_db):
    settings = Settings()
    async with get_session_factory()() as session:
        product = await _make_product(session)
        result = await scrape_product(session, product, FakeFetcher(PLAIN_PAGE), settings, [], None)
    assert result.ok is False


async def test_renderer_availability_probe_without_playwright(monkeypatch):
    import importlib.util

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "playwright" or name.startswith("playwright."):
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    from app.scraping.browser import BrowserRenderer as BR

    probe = BR(Settings())
    assert await probe.is_available() is False
    assert "not installed" in (probe.unavailable_reason or "")
