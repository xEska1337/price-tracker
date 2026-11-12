from app.state import runtime

BASE_URL = "https://example.com/p/1"


async def _create(client, url=BASE_URL, **kwargs):
    return await client.post("/api/products", json={"url": url, **kwargs})


async def test_create_product_scrapes_immediately(client, fake_fetcher):
    resp = await _create(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["last_price"] == 123.45
    assert body["currency"] == "PLN"
    assert body["status"] == "active"
    assert body["title"] == "Test Product XYZ"
    assert body["image_url"] == "https://example.com/img/product.png"
    assert body["sparkline"] == [123.45]
    assert body["next_check_at"] is not None
    assert BASE_URL in fake_fetcher.calls


async def test_duplicate_url_returns_existing(client, fake_fetcher):
    first = await _create(client, url="https://example.com/p/1?utm_source=fb&size=XL")
    assert first.status_code == 201
    dup = await _create(client, url="https://example.com/p/1?size=XL&utm_source=x#g21")
    assert dup.status_code == 200
    assert dup.json()["id"] == first.json()["id"]
    other = await _create(client, url="https://example.com/p/1?size=green")
    assert other.status_code == 201
    assert other.json()["id"] != first.json()["id"]


async def test_invalid_url_rejected(client, fake_fetcher):
    resp = await _create(client, url="just words")
    assert resp.status_code == 422


async def test_detail_range_and_stats(client, fake_fetcher):
    created = (await _create(client)).json()
    pid = created["id"]
    detail = (await client.get(f"/api/products/{pid}?range=all")).json()
    assert detail["range"] == "all"
    assert len(detail["price_points"]) == 1
    assert detail["stats"]["current"] == 123.45
    assert detail["stats"]["at_all_time_low"] is False  

    manual = await client.post(f"/api/products/{pid}/price", json={"price": 99.0})
    assert manual.status_code == 200
    detail = (await client.get(f"/api/products/{pid}?range=7d")).json()
    assert len(detail["price_points"]) == 2
    assert detail["stats"]["min"] == 99.0
    assert detail["stats"]["at_all_time_low"] is True
    assert detail["stats"]["current"] == 99.0

    detail = (await client.get(f"/api/products/{pid}?range=90d")).json()
    assert len(detail["price_points"]) == 2


async def test_detail_404(client, fake_fetcher):
    resp = await client.get("/api/products/does-not-exist")
    assert resp.status_code == 404


async def test_patch_interval_and_pause(client, fake_fetcher):
    pid = (await _create(client)).json()["id"]
    patched = (await client.patch(f"/api/products/{pid}", json={"interval": "6h"})).json()
    assert patched["interval"] == "6h"
    patched = (await client.patch(f"/api/products/{pid}", json={"status": "paused"})).json()
    assert patched["status"] == "paused"
    patched = (await client.patch(f"/api/products/{pid}", json={"status": "active"})).json()
    assert patched["status"] == "active"


async def test_scrape_now_success_and_failure_backoff(client, fake_fetcher):
    created = (await _create(client)).json()
    pid = created["id"]
    ok = await client.post(f"/api/products/{pid}/scrape")
    assert ok.status_code == 200
    assert ok.json()["status"] == "active"

    fake_fetcher.fail_urls[BASE_URL] = "boom"
    await client.post(f"/api/products/{pid}/scrape")
    body = (await client.post(f"/api/products/{pid}/scrape")).json()
    assert body["status"] == "failed"  
    assert body["next_check_at"] is not None

    fake_fetcher.fail_urls.clear()
    recovered = (await client.post(f"/api/products/{pid}/scrape")).json()
    assert recovered["status"] == "active"
    assert recovered["last_price"] == 123.45


async def test_delete_product_cascades(client, fake_fetcher):
    pid = (await _create(client)).json()["id"]
    resp = await client.delete(f"/api/products/{pid}")
    assert resp.status_code == 204
    assert (await client.get(f"/api/products/{pid}")).status_code == 404
    assert (await client.get("/api/products")).json() == []


async def test_list_order_newest_first(client, fake_fetcher):
    a = (await _create(client, url="https://example.com/a")).json()
    b = (await _create(client, url="https://example.com/b")).json()
    listing = (await client.get("/api/products")).json()
    assert [p["id"] for p in listing] == [b["id"], a["id"]]


async def test_health(client, fake_fetcher):
    body = (await client.get("/api/health")).json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["products"] == 0


async def test_deals_endpoints(client, fake_fetcher):

    body = (await client.get("/api/deals")).json()
    assert body["deals"] == []
    assert body["fetched_at"] is None

    fake_fetcher.feed_payload = (
        b'<rss><channel><item><title>Hit</title>'
        b"<link>https://www.pepper.pl/promocja/hit</link>"
        b"<pubDate>Tue, 11 Nov 2026 10:00:00 +0000</pubDate></item></channel></rss>"
    )
    refresh = await client.post("/api/deals/refresh")
    assert refresh.status_code == 200
    assert refresh.json()["count"] == 1
    assert refresh.json()["fetched_at"] is not None
    assert runtime.rss_fetched_at is not None

    body = (await client.get("/api/deals")).json()
    assert len(body["deals"]) == 1
    assert body["deals"][0]["title"] == "Hit"

    refresh = await client.post("/api/deals/refresh")
    assert refresh.json()["count"] == 0
    assert len((await client.get("/api/deals")).json()["deals"]) == 1
