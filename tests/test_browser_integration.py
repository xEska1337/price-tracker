import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("PRICETRACK_BROWSER_TESTS") != "1",
    reason="set PRICETRACK_BROWSER_TESTS=1 and install playwright + chromium to run",
)

JS_PAGE = """<html><head><title>JS shop</title></head><body>
<h1>Wireless Keyboard</h1>
<script>
setTimeout(function () {
  var s = document.createElement('script');
  s.type = 'application/ld+json';
  s.textContent = JSON.stringify({
    "@context": "https://schema.org", "@type": "Product",
    "name": "Wireless Keyboard",
    "image": "https://js.example/kb.png",
    "offers": {"@type": "Offer", "price": "329.00", "priceCurrency": "PLN",
               "availability": "https://schema.org/InStock"}
  });
  document.head.appendChild(s);
}, 400);
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  
        body = JS_PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def js_page_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/product"
    server.shutdown()


async def test_browser_renders_js_injected_price(js_page_url):
    from app.config import Settings
    from app.scraping.browser import BrowserRenderer
    from app.scraping.extract import extract_all

    renderer = BrowserRenderer(Settings())
    try:
        available = await renderer.is_available()
        assert available, renderer.unavailable_reason
        html, final_url = await renderer.render(js_page_url)
        data = extract_all(html, final_url)
        assert data.price == 329.0
        assert "jsonld" in (data.extractor or "")
    finally:
        await renderer.aclose()


async def test_plain_fetch_has_no_price(js_page_url):
    import httpx

    response = httpx.get(js_page_url)
    from app.scraping.extract import extract_all

    data = extract_all(response.text, js_page_url)
    assert data.price is None
