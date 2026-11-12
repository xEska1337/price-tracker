
import httpx
import pytest

from app.config import Settings
from app.images import ImageProxy, ImageProxyError

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def make_proxy(tmp_path, handler, resolver=None):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    settings = Settings(image_cache_dir=str(tmp_path / "cache"), image_cache_ttl_days=7)
    return ImageProxy(settings, client=client, resolver=resolver or public_resolver)


async def public_resolver(host):
    return ["93.184.216.34"]


def image_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=PNG)


async def test_fetches_and_caches(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return image_handler(request)

    resolver_calls = []

    async def resolver(host):
        resolver_calls.append(host)
        return ["93.184.216.34"]

    proxy = make_proxy(tmp_path, handler, resolver)
    data, ctype, etag = await proxy.fetch("https://cdn.example.com/a.jpg")
    assert data == PNG and ctype == "image/jpeg" and len(etag) == 32
    data2, _, etag2 = await proxy.fetch("https://cdn.example.com/a.jpg")
    assert data2 == PNG and etag2 == etag
    assert len(calls) == 1
    assert len(resolver_calls) == 1
    await proxy.aclose()


async def test_rejects_private_addresses(tmp_path):
    async def private_resolver(host):
        return ["10.0.0.5"]

    proxy = make_proxy(tmp_path, image_handler, private_resolver)
    with pytest.raises(ImageProxyError) as exc:
        await proxy.fetch("https://internal.example.com/a.jpg")
    assert exc.value.status == 400
    await proxy.aclose()


async def test_rejects_localhost_and_bad_schemes(tmp_path):
    proxy = make_proxy(tmp_path, image_handler)

    async def loopback_resolver(host):
        return ["127.0.0.1"]

    proxy._resolver = loopback_resolver
    with pytest.raises(ImageProxyError):
        await proxy.fetch("http://localhost/a.jpg")
    with pytest.raises(ImageProxyError):
        await proxy.fetch("file:///etc/passwd")
    with pytest.raises(ImageProxyError):
        await proxy.fetch("https://cdn.example.com:8080/a.jpg")  
    await proxy.aclose()


async def test_rejects_non_image_content(tmp_path):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>")

    proxy = make_proxy(tmp_path, handler)
    with pytest.raises(ImageProxyError) as exc:
        await proxy.fetch("https://cdn.example.com/page")
    assert exc.value.status == 502 and "not return an image" in exc.value.detail
    await proxy.aclose()


async def test_rejects_oversized(tmp_path):
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "image/png", "content-length": str(10 * 1024 * 1024)},
            content=b"x",
        )

    settings = Settings(image_cache_dir=str(tmp_path / "cache"), image_max_bytes=1024)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    proxy = ImageProxy(settings, client=client, resolver=public_resolver)
    with pytest.raises(ImageProxyError) as exc:
        await proxy.fetch("https://cdn.example.com/big.png")
    assert "too large" in exc.value.detail.lower()
    await proxy.aclose()


async def test_follows_redirects_but_revalidates(tmp_path):
    def handler(request):
        if request.url.path == "/start.jpg":
            return httpx.Response(302, headers={"location": "/real.jpg"})
        return image_handler(request)

    proxy = make_proxy(tmp_path, handler)
    data, ctype, _ = await proxy.fetch("https://cdn.example.com/start.jpg")
    assert data == PNG and ctype == "image/jpeg"
    await proxy.aclose()


async def test_redirect_to_private_host_is_blocked(tmp_path):
    def handler(request):
        return httpx.Response(302, headers={"location": "http://10.0.0.9/secret.jpg"})

    async def resolver(host):
        return ["93.184.216.34"] if "cdn.example.com" in host else ["10.0.0.9"]

    proxy = make_proxy(tmp_path, handler, resolver)
    with pytest.raises(ImageProxyError) as exc:
        await proxy.fetch("https://cdn.example.com/start.jpg")
    assert exc.value.status == 400
    await proxy.aclose()


async def test_upstream_errors_become_502(tmp_path):
    def handler(request):
        return httpx.Response(404)

    proxy = make_proxy(tmp_path, handler)
    with pytest.raises(ImageProxyError) as exc:
        await proxy.fetch("https://cdn.example.com/missing.jpg")
    assert exc.value.status == 502
    await proxy.aclose()


async def test_api_endpoint_serves_cache_and_304(client, fake_fetcher, tmp_path, monkeypatch):
    from app.state import runtime

    def handler(request):
        return image_handler(request)

    proxy = make_proxy(tmp_path, handler)
    monkeypatch.setattr(runtime, "image_proxy", proxy)
    try:
        url = "https://cdn.example.com/product.png"
        resp = await client.get("/api/image", params={"url": url})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert resp.headers["cache-control"].startswith("public")
        etag = resp.headers["etag"]

        revalidated = await client.get("/api/image", params={"url": url}, headers={"If-None-Match": etag})
        assert revalidated.status_code == 304

        blocked = await client.get("/api/image", params={"url": "ftp://x/y.jpg"})
        assert blocked.status_code == 400
    finally:
        await proxy.aclose()


async def test_cache_entries_are_pruned(tmp_path):
    settings = Settings(
        image_cache_dir=str(tmp_path / "cache"),
        image_cache_max_mb=0,  
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(image_handler))
    proxy = ImageProxy(settings, client=client, resolver=public_resolver)
    await proxy.fetch("https://cdn.example.com/one.jpg")
    await proxy.aclose()
    remaining = list((tmp_path / "cache").glob("*.bin"))
    assert remaining == []


async def test_proxy_disabled_redirects_to_original(client, fake_fetcher, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("IMAGE_PROXY_ENABLED", "false")
    get_settings.cache_clear()
    try:
        url = "https://cdn.example.com/product.png"
        resp = await client.get("/api/image", params={"url": url}, follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == url
    finally:
        monkeypatch.delenv("IMAGE_PROXY_ENABLED", raising=False)
        get_settings.cache_clear()
