from bs4 import BeautifulSoup

from app.scraping.adapters import Adapter, load_adapters, match_adapter
from app.scraping.extract import extract_all
from app.scraping.extract.jsonld import extract_jsonld

JSONLD_PAGE = """
<html><head>
<meta property="og:title" content="OG Title">
<script type="application/ld+json">
{"@graph":[
 {"@type":"BreadcrumbList"},
 {"@type":"Product","name":"Klawiatura Logitech G29",
  "image":{"@id":"https://cdn.example.com/img1.jpg"},
  "offers":[{"@type":"AggregateOffer","offers":[
     {"@type":"Offer","price":"1 199,00","priceCurrency":"PLN","availability":"https://schema.org/OutOfStock"},
     {"@type":"Offer","price":"1099.00","priceCurrency":"PLN","availability":"https://schema.org/InStock"}
  ]}]
 }
]}
</script>
</head></html>
"""

OG_ONLY_PAGE = """
<html><head>
<meta property="og:title" content="Słuchawki Sony">
<meta property="og:image" content="/media/222.jpg">
<meta property="product:price:amount" content="459,00">
<meta property="product:price:currency" content="PLN">
</head></html>
"""

ADAPTER_PAGE = """
<html><body>
<h1 class="pname">Żarówka LED 9W</h1>
<span class="price">89,99 zł</span>
<img class="pimg" src="https://x.pl/zarowka.jpg">
</body></html>
"""


def test_jsonld_nested_graph_and_offers_list():
    data = extract_jsonld(BeautifulSoup(JSONLD_PAGE, "lxml"))
    assert data is not None
    assert data.title == "Klawiatura Logitech G29"
    assert data.price == 1099.00  
    assert data.currency == "PLN"
    assert data.image == "https://cdn.example.com/img1.jpg"
    assert data.in_stock is True


def test_opengraph_fallback():
    data = extract_all(OG_ONLY_PAGE, "https://shop.example.org/p/1")
    assert data.title == "Słuchawki Sony"
    assert data.price == 459.00
    assert data.currency == "PLN"
    assert data.image == "https://shop.example.org/media/222.jpg"
    assert "opengraph" in data.extractor


def test_adapter_tier_only_when_no_price_found():
    adapter = Adapter(domain="x.pl", selectors={
        "price": "span.price", "title": "h1.pname", "image": "img.pimg"
    }, currency="PLN")
    result = extract_all(ADAPTER_PAGE, "https://x.pl/p/9", adapter)
    assert result.price == 89.99
    assert result.title == "Żarówka LED 9W"
    assert "adapter:x.pl" in result.extractor


def test_adapter_does_not_override_jsonld_price():
    adapter = Adapter(domain="example.com", selectors={"price": ".bogus"}, currency="EUR")
    result = extract_all(JSONLD_PAGE, "https://example.com/p", adapter)
    assert result.price == 1099.00
    assert result.currency == "PLN"


def test_match_adapter_suffix_and_specificity(tmp_path):
    (tmp_path / "example.json").write_text(
        '{"domain": "example.com", "selectors": {"price": ".p"}}', encoding="utf-8"
    )
    (tmp_path / "shop.json").write_text(
        '{"domain": "shop.example.com", "selectors": {"price": ".p"}}', encoding="utf-8"
    )
    adapters = load_adapters(tmp_path)
    assert match_adapter("www.example.com", adapters) is not None
    assert match_adapter("evil-example.com", adapters) is None
    assert match_adapter("sub.example.com", adapters).domain == "example.com"
    assert match_adapter("shop.example.com", adapters).domain == "shop.example.com"
