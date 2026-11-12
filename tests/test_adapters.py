import json

import pytest

from app.adapters_store import (
    AdapterValidationError,
    list_user_adapters,
    parse_adapter_json,
    validate_adapter,
)
from app.config import get_settings
from app.scraping.prompt import build_adapter_prompt, clean_html, find_price_candidates

PAGE = """
<html><head><title>Shop</title>
<script>var x = 1;</script>
<style>.a{color:red}</style>
<script type="application/ld+json">{"@type": "WebSite"}</script>
</head><body>
<div class="product">
  <h1 class="product-title">Wireless Keyboard</h1>
  <img class="product-image" src="/kb.png">
  <div class="price-block">
    <span class="price-value" data-testid="price">1 299,00 zł</span>
    <span class="old-price">1 499,00 zł</span>
  </div>
  <button onclick="buy()">Buy</button>
</div>
</body></html>
"""


def test_clean_html_removes_scripts_and_handlers():
    cleaned = clean_html(PAGE)
    assert "var x = 1" not in cleaned
    assert "color:red" not in cleaned
    assert "onclick" not in cleaned
    assert "1 299,00 zł" in cleaned
    assert len(cleaned) < len(PAGE) * 2  


def test_find_price_candidates():
    candidates = find_price_candidates(PAGE)
    assert candidates
    joined = "\n".join(candidates)
    assert "1 299,00 zł" in joined
    assert "price-value" in joined


def test_prompt_contains_schema_and_page_context():
    prompt = build_adapter_prompt("https://shop.example.com/p/1", PAGE, "shop.example.com")
    assert "PriceTrack" in prompt
    assert '"price"' in prompt and '"selectors"' in prompt
    assert "shop.example.com" in prompt
    assert "1 299,00 zł" in prompt  
    assert "```json" in prompt
    assert "No XPath" in prompt or "No XPath" in prompt


def test_prompt_truncates_large_pages():
    big = "<html><body>" + ("<div class='x'>text</div>" * 5000) + "</body></html>"
    prompt = build_adapter_prompt("https://shop.example.com/p", big)
    assert len(prompt) <= 18_000


def test_parse_adapter_tolerates_fenced_json():
    text = 'Sure! Here is your adapter:\n```json\n{"domain": "shop.example.com", "selectors": {"price": ".price"}}\n```'
    spec = parse_adapter_json(text)
    assert spec["selectors"]["price"] == ".price"


def test_parse_adapter_rejects_garbage():
    with pytest.raises(AdapterValidationError):
        parse_adapter_json("no json here")
    with pytest.raises(AdapterValidationError):
        parse_adapter_json('{"domain": "x.com", "selectors": ')


def test_validate_adapter_normalizes_and_checks():
    domain, clean = validate_adapter(
        {"domain": "WWW.Shop.Example.COM", "currency": "pln", "selectors": {"price": ".price-value"}},
        expected_domain="shop.example.com",
    )
    assert domain == "shop.example.com"
    assert clean["currency"] == "PLN"
    assert clean["selectors"]["price"] == ".price-value"


def test_validate_adapter_rejects_mismatch_and_bad_selectors():
    with pytest.raises(AdapterValidationError):
        validate_adapter({"domain": "evil.com", "selectors": {"price": ".p"}}, "shop.example.com")
    with pytest.raises(AdapterValidationError):
        validate_adapter({"domain": "shop.example.com", "selectors": {"title": "h1"}})  
    with pytest.raises(AdapterValidationError):
        validate_adapter({"domain": "shop.example.com", "selectors": {"price": "div[["}})
    with pytest.raises(AdapterValidationError):
        validate_adapter({"domain": "not a domain", "selectors": {"price": ".p"}})




@pytest.fixture
def isolated_adapters(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTERS_DIR", str(tmp_path / "adapters"))
    get_settings.cache_clear()
    yield tmp_path / "adapters"
    get_settings.cache_clear()


UNPRICED_URL = "https://shop.example.com/adapter-demo"


async def _make_unsupported(client, fake_fetcher):
    fake_fetcher.html_by_url[UNPRICED_URL] = PAGE  
    resp = await client.post(
        "/api/products", json={"url": UNPRICED_URL, "interval": "24h"}
    )
    body = resp.json()
    assert body["status"] == "unsupported"
    return body


async def test_adapter_prompt_endpoint(client, fake_fetcher, isolated_adapters):
    product = await _make_unsupported(client, fake_fetcher)
    resp = await client.post(f"/api/products/{product['id']}/adapter-prompt")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "shop.example.com"
    assert '"price"' in body["prompt"]
    assert "1 299,00 zł" in body["prompt"]


async def test_install_adapter_tests_and_activates_product(client, fake_fetcher, isolated_adapters):
    product = await _make_unsupported(client, fake_fetcher)
    adapter = {
        "domain": "shop.example.com",
        "currency": "PLN",
        "selectors": {"price": ".price-value", "title": "h1.product-title"},
    }
    resp = await client.post(
        "/api/adapters", json={"product_id": product["id"], "adapter": json.dumps(adapter)}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["price"] == 1299.0
    assert body["product"]["status"] == "active"
    assert body["product"]["last_price"] == 1299.0

    saved = list_user_adapters()
    assert saved and saved[0]["domain"] == "shop.example.com"
    assert (isolated_adapters / "shop.example.com.json").is_file()


async def test_install_adapter_rejects_wrong_selector(client, fake_fetcher, isolated_adapters):
    product = await _make_unsupported(client, fake_fetcher)
    bad = {"domain": "shop.example.com", "selectors": {"price": ".does-not-exist"}}
    resp = await client.post(
        "/api/adapters", json={"product_id": product["id"], "adapter": json.dumps(bad)}
    )
    assert resp.status_code == 422
    assert "did not match" in resp.json()["detail"]
    assert not list_user_adapters()


async def test_install_adapter_rejects_invalid_json(client, fake_fetcher, isolated_adapters):
    product = await _make_unsupported(client, fake_fetcher)
    resp = await client.post(
        "/api/adapters", json={"product_id": product["id"], "adapter": "not json at all"}
    )
    assert resp.status_code == 422


async def test_delete_user_adapter(client, fake_fetcher, isolated_adapters):
    product = await _make_unsupported(client, fake_fetcher)
    adapter = {"domain": "shop.example.com", "selectors": {"price": ".price-value"}}
    await client.post("/api/adapters", json={"product_id": product["id"], "adapter": json.dumps(adapter)})
    assert (await client.delete("/api/adapters/shop.example.com")).status_code == 204
    assert list_user_adapters() == []
    assert (await client.delete("/api/adapters/shop.example.com")).status_code == 404


async def test_installed_adapter_is_used_by_normal_scrapes(client, fake_fetcher, isolated_adapters):
    product = await _make_unsupported(client, fake_fetcher)
    adapter = {"domain": "shop.example.com", "selectors": {"price": ".price-value"}}
    await client.post("/api/adapters", json={"product_id": product["id"], "adapter": json.dumps(adapter)})

    resp = await client.post(f"/api/products/{product['id']}/scrape")
    body = resp.json()
    assert body["status"] == "active"
    assert body["last_price"] == 1299.0


def test_normalize_domain_accepts_ips_and_localhost():
    from app.adapters_store import normalize_domain

    assert normalize_domain("127.0.0.1") == "127.0.0.1"
    assert normalize_domain("http://localhost:8099/x") == "localhost"
    assert normalize_domain("https://www.shop.example.com/p") == "shop.example.com"
    with pytest.raises(AdapterValidationError):
        normalize_domain("not a domain")


async def test_get_installed_adapter_json(client, fake_fetcher, isolated_adapters):
    product = await _make_unsupported(client, fake_fetcher)
    adapter = {
        "domain": "shop.example.com",
        "currency": "PLN",
        "selectors": {"price": ".price-value", "title": "h1.product-title"},
    }
    await client.post("/api/adapters", json={"product_id": product["id"], "adapter": json.dumps(adapter)})

    resp = await client.get("/api/adapters/shop.example.com")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "shop.example.com"
    assert body["selectors"]["price"] == ".price-value"
    assert body["currency"] == "PLN"

    missing = await client.get("/api/adapters/other.example.com")
    assert missing.status_code == 404
