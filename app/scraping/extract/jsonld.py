from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from app.scraping.data import ExtractedData
from app.scraping.pricing import parse_price_number

_IN_STOCK_WORDS = ("instock", "available", "inlineonly", "limitedavailability", "preorder")
_OUT_STOCK_WORDS = ("outofstock", "soldout", "discontinued")


def _types(node: dict) -> set[str]:
    t = node.get("@type")
    if isinstance(t, str):
        return {t.lower()}
    if isinstance(t, list):
        return {str(x).lower() for x in t}
    return set()


def _iter_nodes(data: Any, depth: int = 0):
    if depth > 6:
        return
    if isinstance(data, list):
        for item in data:
            yield from _iter_nodes(item, depth + 1)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "mainEntity", "itemListElement", "item", "isRelatedTo", "about"):
            if key in data:
                yield from _iter_nodes(data[key], depth + 1)


def _image_from(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _image_from(value[0])
    if isinstance(value, dict):
        for key in ("url", "@id", "contentUrl", "thumbnailUrl"):
            v = value.get(key)
            if isinstance(v, str):
                return v
    return None


def _has_price(offer: dict) -> bool:
    return parse_price_number(offer.get("price")) is not None or parse_price_number(
        offer.get("lowPrice")
    ) is not None


def _is_in_stock_offer(offer: dict) -> bool:
    avail = str(offer.get("availability", "")).lower()
    return any(w in avail for w in _IN_STOCK_WORDS)


def _pick_offer(offers: Any) -> dict | None:
    if isinstance(offers, list):
        candidates = [o for o in offers if isinstance(o, dict)]
        if not candidates:
            return None
        for offer in candidates:
            if _has_price(offer) and _is_in_stock_offer(offer):
                return offer
        for offer in candidates:
            if _has_price(offer):
                return offer
        for candidate in candidates:
            if candidate.get("offers") is not None:
                picked = _pick_offer(candidate.get("offers"))
                if picked is not None:
                    return picked
            if parse_price_number(candidate.get("lowPrice")) is not None:
                return candidate
        return candidates[0]
    if isinstance(offers, dict):
        nested = offers.get("offers")
        if nested is not None:  
            picked = _pick_offer(nested)
            if picked is not None:
                return picked
            if parse_price_number(offers.get("lowPrice")) is not None:
                return offers
        return offers
    return None


def _product_from(node: dict) -> ExtractedData | None:
    offer = _pick_offer(node.get("offers"))
    price = None
    currency = None
    in_stock = True
    if offer:
        price = parse_price_number(offer.get("price")) or parse_price_number(offer.get("lowPrice"))
        currency = offer.get("priceCurrency")
        avail = str(offer.get("availability", "")).lower()
        if any(w in avail for w in _OUT_STOCK_WORDS):
            in_stock = False
    title = node.get("name")
    if not isinstance(title, str):
        return None
    data = ExtractedData(
        title=title.strip() or None,
        image=_image_from(node.get("image")),
        price=price,
        currency=(currency or "").upper() or None,
        in_stock=in_stock,
        extractor="jsonld",
    )
    if data.is_empty():
        return None
    return data


def extract_jsonld(soup: BeautifulSoup) -> ExtractedData | None:
    best: ExtractedData | None = None
    for script in soup("script", type=lambda t: t and "ld+json" in t):
        raw = script.string or script.get_text()
        if not raw:
            continue
        raw = raw.strip()
        if not raw.startswith(("{", "[")):
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _iter_nodes(parsed):
            if "product" not in _types(node):
                continue
            data = _product_from(node)
            if data is None:
                continue
            if data.has_price():
                return data
            best = best or data
    return best
