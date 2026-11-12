import pytest

from app.config import get_settings


@pytest.fixture
def auth_mode(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "sekret")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_requires_login_when_password_enabled(client, fake_fetcher, auth_mode):
    resp = await client.get("/api/products")
    assert resp.status_code == 401

    assert (await client.get("/api/health")).status_code == 200


async def test_wrong_password_rejected(client, fake_fetcher, auth_mode):
    resp = await client.post("/api/login", json={"password": "zle"})
    assert resp.status_code == 401


async def test_login_sets_session_cookie_and_unlocks(client, fake_fetcher, auth_mode):
    login = await client.post("/api/login", json={"password": "sekret"})
    assert login.status_code == 200
    assert "pt_session" in client.cookies

    assert (await client.get("/api/products")).status_code == 200
    created = await client.post("/api/products", json={"url": "https://example.com/p/auth"})
    assert created.status_code == 201


async def test_login_fails_closed_without_password_config(client, fake_fetcher, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    get_settings.cache_clear()
    resp = await client.post("/api/login", json={"password": ""})
    assert resp.status_code == 401
    get_settings.cache_clear()
