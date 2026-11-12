from __future__ import annotations

import calendar
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
from bs4 import BeautifulSoup

_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
_MERCHANT_RE = re.compile(r"<strong>\s*([^<]+?)\s*[–-]\s*([^<]+?)\s*</strong>", re.I)


def strip_html(html: str) -> str:
    return BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)


def _published(entry: Any) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _image_url(entry: Any) -> str | None:
    for media in entry.get("media_content") or []:
        if media.get("url"):
            return media["url"]
    thumbs = entry.get("media_thumbnail") or []
    if thumbs and thumbs[0].get("url"):
        return thumbs[0]["url"]
    match = _IMG_RE.search(entry.get("description") or "")
    return match.group(1) if match else None


def _merchant_price(entry: Any) -> tuple[str | None, str | None]:
    for key in entry.keys():
        if "merchant" in key.lower():
            value = entry[key]
            if isinstance(value, list):
                value = next((v for v in value if isinstance(v, dict)), None)
            if isinstance(value, dict):
                return value.get("name") or None, value.get("price") or None
    match = _MERCHANT_RE.search(entry.get("description") or "")
    if match:
        return match.group(2).strip(), match.group(1).strip()
    return None, None


def parse_feed(payload: bytes) -> list[dict]:
    feed = feedparser.parse(payload)
    items: list[dict] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        merchant, price_raw = _merchant_price(entry)
        categories = [tag.get("term") for tag in (entry.get("tags") or []) if tag.get("term")]
        snippet = strip_html(entry.get("description") or "")[:220] or None
        items.append(
            {
                "external_id": (entry.get("id") or link).strip()[:500],
                "title": title[:300],
                "link": link,
                "image_url": _image_url(entry),
                "merchant": (merchant or "")[:255] or None,
                "price_raw": (price_raw or "")[:64] or None,
                "category": (categories[0] if categories else "")[:255] or None,
                "snippet": snippet,
                "published_at": _published(entry),
            }
        )
    return items
