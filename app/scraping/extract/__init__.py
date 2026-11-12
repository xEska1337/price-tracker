from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.scraping.adapters import Adapter, extract_via_adapter
from app.scraping.extract.jsonld import extract_jsonld
from app.scraping.extract.opengraph import extract_opengraph
from app.scraping.data import ExtractedData

__all__ = ["ExtractedData", "ScrapeResult", "extract_all"]

from app.scraping.data import ScrapeResult  


def extract_all(html: str, base_url: str, adapter: Adapter | None = None) -> ExtractedData:
    soup = BeautifulSoup(html, "lxml")
    result = ExtractedData()
    result = result.merge_from(extract_jsonld(soup))
    result = result.merge_from(extract_opengraph(soup))
    if not result.has_price() and adapter is not None:
        result = result.merge_from(extract_via_adapter(soup, adapter))
    if result.image:
        result.image = urljoin(base_url, result.image)
    return result
