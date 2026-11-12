from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from app.scraping.data import ExtractedData
from app.scraping.pricing import parse_price_number

ADAPTERS_DIR = Path(__file__).parent / "adapters"


@dataclass
class Adapter:
    domain: str
    selectors: dict[str, str]
    currency: str | None = None

    def matches(self, host: str) -> bool:
        return host == self.domain or host.endswith("." + self.domain)


def load_adapters(directory: Path | None = None) -> list[Adapter]:
    directory = directory or ADAPTERS_DIR
    adapters: list[Adapter] = []
    if not directory.is_dir():
        return adapters
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("_"):
            continue  
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            adapters.append(
                Adapter(domain=raw["domain"].lower(), selectors=raw.get("selectors", {}),
                        currency=raw.get("currency"))
            )
        except (json.JSONDecodeError, KeyError):
            continue
    return sorted(adapters, key=lambda a: a.domain.count("."), reverse=True)


def match_adapter(host: str, adapters: list[Adapter]) -> Adapter | None:
    for adapter in adapters:  
        if adapter.domain == host:
            return adapter
    for adapter in adapters:
        if adapter.matches(host):
            return adapter
    return None


def _node_value(el) -> str | None:
    if el.name in ("meta", "link"):
        return el.get("content") or el.get("href")
    for attr in ("src", "data-src", "data-srcset", "content", "href", "data-src-full"):
        if el.get(attr):
            return el[attr]
    return el.get_text(strip=True) or None


def extract_via_adapter(soup: BeautifulSoup, adapter: Adapter) -> ExtractedData | None:
    data = ExtractedData(extractor=f"adapter:{adapter.domain}")
    for field, selector in adapter.selectors.items():
        el = soup.select_one(selector)
        if el is None:
            continue
        value = _node_value(el)
        if not value:
            continue
        if field == "price":
            data.price = parse_price_number(value)
            data.currency = adapter.currency or "PLN"
        elif field == "title":
            data.title = value
        elif field == "image":
            data.image = value
    return None if data.is_empty() else data
