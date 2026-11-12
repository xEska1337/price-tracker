from __future__ import annotations

from bs4 import BeautifulSoup

from app.scraping.data import ExtractedData
from app.scraping.pricing import guess_currency, parse_price_number


def _meta(soup: BeautifulSoup, *keys: str) -> str | None:
    for key in keys:
        el = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if el and el.get("content"):
            return el["content"].strip()
    return None


def extract_opengraph(soup: BeautifulSoup) -> ExtractedData | None:
    price_raw = _meta(soup, "product:price:amount", "og:price:amount", "twitter:data1")
    price = parse_price_number(price_raw)
    data = ExtractedData(
        title=_meta(soup, "og:title"),
        image=_meta(soup, "og:image", "og:image:url"),
        price=price,
        currency=(_meta(soup, "product:price:currency", "og:price:currency") or guess_currency(price_raw)),
        extractor="opengraph",
    )
    return None if data.is_empty() else data
