from datetime import datetime, timezone

import httpx

from app.config import Settings, get_settings
from app.db.models import Product
from app.notifications import discord
from app.notifications.discord import build_price_drop_payload, should_notify


def make_product() -> Product:
    return Product(
        id="p1",
        url="https://shop.example/p/1",
        url_canonical="https://shop.example/p/1",
        domain="shop.example",
        title="Fancy Headphones",
        image_url="https://shop.example/img.jpg",
        currency="PLN",
        interval="24h",
        last_price=499.0,
        created_at=datetime.now(timezone.utc),
    )


def settings_with(**overrides) -> Settings:
    return Settings(**overrides)


def test_payload_contains_price_change_and_link():
    payload = build_price_drop_payload(
        product=make_product(), old_price=499.0, new_price=449.0,
        currency="PLN", is_all_time_low=True,
    )
    embed = payload["embeds"][0]
    assert embed["title"] == "Price drop: Fancy Headphones"
    assert embed["url"] == "https://shop.example/p/1"
    assert "499.00 PLN" in embed["fields"][0]["value"]
    assert "449.00 PLN" in embed["fields"][0]["value"]
    assert "-10.0%" in embed["fields"][0]["value"]
    assert embed["thumbnail"]["url"] == "https://shop.example/img.jpg"
    assert any("All-time low" in f["name"] for f in embed["fields"])
    assert embed["color"] == discord.GREEN


def test_payload_without_all_time_low_uses_amber_and_no_callout():
    payload = build_price_drop_payload(
        product=make_product(), old_price=499.0, new_price=479.0,
        currency="PLN", is_all_time_low=False,
    )
    embed = payload["embeds"][0]
    assert embed["color"] == discord.AMBER
    assert not any("All-time low" in f["name"] for f in embed["fields"])


def test_payload_handles_missing_image_and_currency():
    product = make_product()
    product.image_url = None
    product.currency = None
    payload = build_price_drop_payload(
        product=product, old_price=100.0, new_price=90.0,
        currency=None, is_all_time_low=False,
    )
    embed = payload["embeds"][0]
    assert "thumbnail" not in embed
    assert "PLN" in embed["fields"][0]["value"]


def test_should_notify_gates():
    s = settings_with(discord_webhook_url="https://discord.test/hook")
    assert not should_notify(settings=s, old_price=100.0, new_price=100.0, is_all_time_low=False)
    assert not should_notify(settings=s, old_price=100.0, new_price=110.0, is_all_time_low=False)
    assert not should_notify(settings=settings_with(), old_price=100.0, new_price=90.0,
                             is_all_time_low=False)
    assert not should_notify(settings=s, old_price=None, new_price=90.0, is_all_time_low=False)
    assert should_notify(settings=s, old_price=100.0, new_price=90.0, is_all_time_low=False)


def test_min_drop_threshold():
    s = settings_with(discord_webhook_url="https://discord.test/hook", discord_min_drop_pct=10.0)
    assert not should_notify(settings=s, old_price=100.0, new_price=95.0, is_all_time_low=True)
    assert should_notify(settings=s, old_price=100.0, new_price=89.0, is_all_time_low=True)


async def test_post_webhook_success_and_failure(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False

        async def post(self, url, json=None):
            calls.append({"url": url, "json": json})
            if "fail" in url:
                raise httpx.ConnectError("boom")
            return httpx.Response(204 if "ok" in url else 400, request=httpx.Request("POST", url))

    monkeypatch.setattr(discord.httpx, "AsyncClient", FakeClient)
    assert await discord.post_webhook("https://discord.test/ok", {"a": 1}) is True
    assert await discord.post_webhook("https://discord.test/fail", {"a": 2}) is False
    assert await discord.post_webhook("https://discord.test/reject", {"a": 3}) is False
    assert len(calls) == 3


async def test_notify_price_drop_respects_config(monkeypatch):
    sent = []

    async def fake_post(url, payload):
        sent.append(url)
        return True

    monkeypatch.setattr(discord, "post_webhook", fake_post)
    product = make_product()

    off = settings_with()
    assert await discord.notify_price_drop(
        settings=off, product=product, old_price=100.0, new_price=90.0, is_all_time_low=False
    ) is False
    assert sent == []

    on = settings_with(discord_webhook_url="https://discord.test/hook")
    assert await discord.notify_price_drop(
        settings=on, product=product, old_price=100.0, new_price=90.0, is_all_time_low=False
    ) is True
    assert sent == ["https://discord.test/hook"]


async def test_notifications_status_and_test_endpoint(client, fake_fetcher, monkeypatch):
    status = (await client.get("/api/notifications")).json()
    assert status["discord"]["enabled"] is False
    assert (await client.post("/api/notifications/test")).status_code == 400

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    get_settings.cache_clear()

    async def ok_post(url, payload):
        return True

    monkeypatch.setattr(discord, "post_webhook", ok_post)
    status = (await client.get("/api/notifications")).json()
    assert status["discord"]["enabled"] is True
    resp = await client.post("/api/notifications/test")
    assert resp.status_code == 200 and resp.json()["sent"] is True
    get_settings.cache_clear()
