
from app.notifications import discord

VALID_HOOK = "https://discord.com/api/webhooks/123456789/abcdefTOKEN_-x"


async def test_get_settings_defaults(client, fake_fetcher):
    body = (await client.get("/api/settings")).json()
    assert body["discord"]["configured"] is False
    assert body["discord"]["webhook_url"] == ""
    assert body["discord"]["min_drop_pct"] == 0.0
    assert body["discord"]["highlight_all_time_low"] is True
    assert "enabled" in body["browser"] and "available" in body["browser"]


async def test_put_rejects_malformed_webhook(client, fake_fetcher):
    resp = await client.put("/api/settings", json={"discord": {"webhook_url": "https://example.com/hook"}})
    assert resp.status_code == 422


async def test_put_saves_webhook_and_reflects_in_status(client, fake_fetcher):
    resp = await client.put(
        "/api/settings",
        json={"discord": {"webhook_url": VALID_HOOK, "min_drop_pct": 5, "highlight_all_time_low": False}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["discord"]["webhook_url"] == VALID_HOOK
    assert body["discord"]["configured"] is True
    assert body["discord"]["min_drop_pct"] == 5
    assert body["discord"]["highlight_all_time_low"] is False

    again = (await client.get("/api/settings")).json()
    assert again["discord"]["webhook_url"] == VALID_HOOK

    status = (await client.get("/api/notifications")).json()
    assert status["discord"]["enabled"] is True
    assert status["discord"]["min_drop_pct"] == 5


async def test_clearing_webhook_disables(client, fake_fetcher):
    await client.put("/api/settings", json={"discord": {"webhook_url": VALID_HOOK}})
    resp = await client.put("/api/settings", json={"discord": {"webhook_url": ""}})
    assert resp.json()["discord"]["configured"] is False
    assert (await client.post("/api/notifications/test")).status_code == 400


async def test_test_endpoint_uses_saved_webhook(client, fake_fetcher, monkeypatch):
    sent = []

    async def fake_post(url, payload):
        sent.append((url, payload))
        return True

    monkeypatch.setattr(discord, "post_webhook", fake_post)
    await client.put("/api/settings", json={"discord": {"webhook_url": VALID_HOOK}})
    resp = await client.post("/api/notifications/test")
    assert resp.status_code == 200 and resp.json()["sent"] is True
    assert sent[0][0] == VALID_HOOK
    assert sent[0][1]["embeds"][0]["title"] == "PriceTrack test notification"


async def test_scrape_notification_uses_ui_webhook(client, fake_fetcher, monkeypatch):
    sent = []

    async def fake_post(url, payload):
        sent.append(url)
        return True

    monkeypatch.setattr(discord, "post_webhook", fake_post)
    await client.put("/api/settings", json={"discord": {"webhook_url": VALID_HOOK}})

    product = (await client.post("/api/products", json={"url": "https://example.com/p/drop"})).json()
    assert product["last_price"] == 123.45

    from app.db.models import Product
    from app.db.session import get_session_factory

    async with get_session_factory()() as session:
        row = await session.get(Product, product["id"])
        row.last_price = 199.0
        await session.commit()

    resp = await client.post(f"/api/products/{product['id']}/scrape")
    assert resp.status_code == 200
    assert sent == [VALID_HOOK]


async def test_playwright_toggle_persists(client, fake_fetcher):
    body = (await client.put("/api/settings", json={"playwright_enabled": False})).json()
    assert body["browser"]["enabled"] is False
    assert (await client.get("/api/settings")).json()["browser"]["enabled"] is False
    body = (await client.put("/api/settings", json={"playwright_enabled": True})).json()
    assert body["browser"]["enabled"] is True
