from app.config import Settings
from app.db.models import Product
from app.db.session import get_session_factory
from app.scraping.service import scrape_product

PAGE_WITHOUT_PRICE = "<html><head><title>Some page</title></head><body><h1>No price here</h1></body></html>"


class FetcherWithoutPrice:
    def __init__(self, status: int = 200):
        self.status = status

    async def get_text(self, url):
        return PAGE_WITHOUT_PRICE, url, self.status

    async def get_bytes(self, url):
        return b""


async def _new_product(session, url="https://shop.example/no-price"):
    product = Product(
        url=url,
        url_canonical=url,
        domain="shop.example",
        interval="24h",
        status="active",
    )
    session.add(product)
    await session.commit()
    return product


async def test_unreadable_price_marks_product_unsupported_with_reason(fresh_db):
    settings = Settings()
    async with get_session_factory()() as session:
        product = await _new_product(session)
        result = await scrape_product(session, product, FetcherWithoutPrice(), settings, [], None)

    assert result.ok is False
    assert result.failure_kind == "extract"
    assert product.status == "unsupported"
    assert product.last_error
    assert "No price found" in product.last_error
    assert "JavaScript" in product.last_error
    assert product.last_price is None


async def test_unsupported_product_is_retried_by_scheduler_filter(fresh_db):
    from sqlalchemy import select


    async with get_session_factory()() as session:
        product = await _new_product(session, url="https://shop.example/retry")
        await scrape_product(session, product, FetcherWithoutPrice(), Settings(), [], None)
        assert product.status == "unsupported"
        from app.db.models import utcnow

        product.next_check_at = utcnow()
        await session.commit()
        rows = (
            await session.execute(
                select(Product).where(Product.status.in_(("active", "failed", "unsupported")))
            )
        ).scalars().all()
        assert product.id in {row.id for row in rows}


async def test_network_error_is_failed_only_after_second_strike(fresh_db):
    class Boom:
        async def get_text(self, url):
            from app.scraping.fetcher import FetchError

            raise FetchError("HTTP 503", status=503)

    settings = Settings()
    async with get_session_factory()() as session:
        product = await _new_product(session, url="https://shop.example/blocked")
        await scrape_product(session, product, Boom(), settings, [], None)
        assert product.status == "active"  
        assert product.last_error and "Could not load the page" in product.last_error
        await scrape_product(session, product, Boom(), settings, [], None)
        assert product.status == "failed"


async def test_success_clears_error_and_restores_active(fresh_db):
    from tests.conftest import PRODUCT_HTML

    class Good:
        async def get_text(self, url):
            return PRODUCT_HTML, url, 200

    settings = Settings()
    async with get_session_factory()() as session:
        product = await _new_product(session, url="https://shop.example/recover")
        await scrape_product(session, product, FetcherWithoutPrice(), settings, [], None)
        assert product.status == "unsupported"
        await scrape_product(session, product, Good(), settings, [], None)
        assert product.status == "active"
        assert product.last_error is None
        assert product.last_price == 123.45


async def test_api_exposes_status_and_last_error(client, fake_fetcher):
    fake_fetcher.html_by_url["https://shop.example/no-price"] = PAGE_WITHOUT_PRICE
    resp = await client.post(
        "/api/products", json={"url": "https://shop.example/no-price", "interval": "24h"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "unsupported"
    assert body["last_price"] is None
    assert body["last_error"] and "No price found" in body["last_error"]

    listing = (await client.get("/api/products")).json()
    assert listing[0]["last_error"] == body["last_error"]


async def test_stores_endpoint_lists_verified_stores(client, fake_fetcher):
    body = (await client.get("/api/stores")).json()
    domains = {store["domain"] for store in body["stores"]}
    assert {"x-kom.pl", "ikea.com", "komputronik.pl", "neonet.pl", "mediaexpert.pl"} <= domains
    assert all(store["verified"] for store in body["stores"])
    assert any(store["tier"] == "browser" for store in body["stores"])
    assert body["tiers"]["jsonld"] == "JSON-LD"
    blocked = {store["domain"] for store in body["blocked"]}
    assert "allegro.pl" in blocked
