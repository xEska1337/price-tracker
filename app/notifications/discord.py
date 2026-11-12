from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.db.models import Product

logger = logging.getLogger(__name__)

GREEN = 0x22C55E
AMBER = 0xF59E0B
TIMEOUT_SECONDS = 10.0
MAX_TITLE = 250


def _fmt(price: float | None, currency: str | None) -> str:
    if price is None:
        return "—"
    return f"{price:,.2f} {currency or 'PLN'}"


def build_price_drop_payload(
    *,
    product: Product,
    old_price: float,
    new_price: float,
    currency: str | None,
    is_all_time_low: bool,
    highlight_all_time_low: bool = True,
) -> dict:
    change = (new_price - old_price) / old_price * 100.0 if old_price else 0.0
    title = product.title or product.url
    embed: dict = {
        "title": f"Price drop: {title}"[:MAX_TITLE],
        "url": product.url,
        "color": GREEN if is_all_time_low else AMBER,
        "fields": [
            {
                "name": "Price",
                "value": f"~~{_fmt(old_price, currency)}~~ → **{_fmt(new_price, currency)}** "
                f"({change:+.1f}%)",
                "inline": False,
            },
            {"name": "Store", "value": product.domain or "—", "inline": True},
            {"name": "Check interval", "value": product.interval, "inline": True},
        ],
        "footer": {"text": "PriceTrack"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if is_all_time_low and highlight_all_time_low:
        embed["fields"].append(
            {"name": "🏆 All-time low", "value": "Lowest price recorded for this product", "inline": False}
        )
    if product.image_url:
        embed["thumbnail"] = {"url": product.image_url}
    return {"username": "PriceTrack", "embeds": [embed]}


async def post_webhook(webhook_url: str, payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(webhook_url, json=payload)
    except httpx.HTTPError as exc:
        logger.warning("Discord notification failed: %s", exc)
        return False
    if response.status_code >= 300:
        logger.warning(
            "Discord notification rejected: HTTP %s %s", response.status_code, response.text[:200]
        )
        return False
    return True


def should_notify(
    *,
    settings: Settings,
    old_price: float | None,
    new_price: float | None,
    is_all_time_low: bool,
) -> bool:
    if not settings.discord_webhook_url or old_price is None or new_price is None:
        return False
    if new_price >= old_price:
        return False
    drop_pct = (old_price - new_price) / old_price * 100.0
    return drop_pct >= settings.discord_min_drop_pct


async def notify_price_drop(
    *,
    settings: Settings,
    product: Product,
    old_price: float,
    new_price: float,
    is_all_time_low: bool,
) -> bool:
    if not should_notify(
        settings=settings, old_price=old_price, new_price=new_price, is_all_time_low=is_all_time_low
    ):
        return False
    payload = build_price_drop_payload(
        product=product,
        old_price=old_price,
        new_price=new_price,
        currency=product.currency,
        is_all_time_low=is_all_time_low,
        highlight_all_time_low=settings.discord_highlight_all_time_low,
    )
    sent = await post_webhook(settings.discord_webhook_url, payload)
    if sent:
        logger.info("Discord price-drop notification sent for product %s", product.id)
    return sent


async def send_test_message(settings: Settings) -> bool:
    payload = {
        "username": "PriceTrack",
        "embeds": [
            {
                "title": "PriceTrack test notification",
                "description": "If you can read this, Discord notifications are configured correctly.",
                "color": GREEN,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
    return await post_webhook(settings.discord_webhook_url, payload)
