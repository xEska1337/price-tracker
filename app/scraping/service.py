from __future__ import annotations

import logging
import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import INTERVAL_SECONDS, Settings
from app.db.models import PricePoint, Product, ScrapeLog, utcnow
from app.notifications.discord import notify_price_drop
from app.scraping.adapters import Adapter, match_adapter
from app.scraping.browser import BrowserRenderer, BrowserUnavailable
from app.scraping.data import ExtractedData
from app.scraping.extract import ScrapeResult, extract_all
from app.scraping.fetcher import FetchError, Fetcher
from app.scraping.normalize import domain_bucket
from app.settings_store import effective_settings

logger = logging.getLogger(__name__)

_BACKOFF_BASE_SECONDS = 900  
_BACKOFF_CAP_SECONDS = 6 * 3600
_FAILURES_BEFORE_FAILED_STATUS = 2


def _schedule_next(product: Product, ok: bool, settings: Settings) -> None:
    interval = INTERVAL_SECONDS.get(product.interval, 24 * 3600)
    now = utcnow()
    if ok:
        product.next_check_at = now + timedelta(seconds=interval + random.uniform(0, 120))
        return
    backoff = min(_BACKOFF_BASE_SECONDS * (2 ** max(product.consecutive_failures - 1, 0)),
                  _BACKOFF_CAP_SECONDS)
    product.next_check_at = now + timedelta(seconds=min(interval, backoff) + random.uniform(0, 60))


async def _previous_low(session: AsyncSession, product_id: str) -> float | None:
    stmt = select(func.min(PricePoint.price)).where(PricePoint.product_id == product_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _try_browser_fallback(
    url: str,
    adapter: Adapter | None,
    settings: Settings,
    renderer: BrowserRenderer | None,
    result: ScrapeResult,
) -> ExtractedData | None:
    if renderer is None or not settings.playwright_enabled:
        return None
    if not await renderer.is_available():
        logger.debug("browser fallback unavailable: %s", renderer.unavailable_reason)
        return None
    try:
        html, final_url = await renderer.render(url)
    except BrowserUnavailable as exc:
        logger.warning("browser fallback unavailable: %s", exc)
        return None
    except Exception as exc:  
        logger.warning("browser fallback failed for %s: %s", url, exc)
        return None
    data = extract_all(html, final_url, adapter)
    if data.extractor:
        data.extractor = f"{data.extractor}+browser"
    result.final_url = final_url
    return data if data.has_price() else None


async def scrape_product(
    session: AsyncSession,
    product: Product,
    fetcher: Fetcher,
    settings: Settings,
    adapters: list[Adapter],
    renderer: BrowserRenderer | None = None,
) -> ScrapeResult:
    settings = await effective_settings(session, settings)
    log = ScrapeLog(product_id=product.id, ok=False)
    product.last_checked_at = utcnow()
    result = ScrapeResult(ok=False)
    old_price = product.last_price

    try:
        html, final_url, status = await fetcher.get_text(product.url)
        result.http_status = status
        result.final_url = final_url
        log.http_status = status
        host = domain_bucket(product.url_canonical or product.url)
        adapter = match_adapter(host, adapters) or match_adapter(domain_bucket(final_url), adapters)
        data = extract_all(html, final_url, adapter)
        result.data = data
        result.extractor = data.extractor
        if not data.has_price():
            fallback = await _try_browser_fallback(product.url, adapter, settings, renderer, result)
            if fallback is not None:
                data = fallback
                result.data = data
                result.extractor = data.extractor
        if data.has_price():
            result.ok = True
        else:
            result.failure_kind = "extract"
            tried = data.extractor or "no structured data"
            result.error = (
                f"No price found on the page (tried: {tried}). "
                "The store may render prices with JavaScript or use an unsupported layout."
            )
            log.error = f"price not found (tried: {tried})"[:500]
    except FetchError as exc:
        result.http_status = exc.status
        result.failure_kind = "network"
        result.error = f"Could not load the page ({exc}). The store may be blocking automated requests."
        log.http_status = exc.status
        log.error = str(exc)[:500]
        host = domain_bucket(product.url_canonical or product.url)
        adapter = match_adapter(host, adapters)
        fallback = await _try_browser_fallback(product.url, adapter, settings, renderer, result)
        if fallback is not None:
            result.data = fallback
            result.extractor = fallback.extractor
            result.ok = True
            result.error = None
            log.error = None
            log.extractor = fallback.extractor

    notified = False
    if result.ok:
        data = result.data
        if data.title:
            product.title = data.title
        if data.image:
            product.image_url = data.image
        product.currency = data.currency or product.currency or "PLN"
        product.last_price = data.price
        product.last_price_at = utcnow()
        session.add(
            PricePoint(product_id=product.id, price=data.price, in_stock=data.in_stock, source="scrape")
        )
        product.consecutive_failures = 0
        product.last_error = None
        if product.status != "paused":
            product.status = "active"
        log.ok = True
        log.extractor = result.extractor
        lowest_before = await _previous_low(session, product.id)
        is_all_time_low = (
            lowest_before is not None and data.price is not None and data.price <= lowest_before
        )
    else:
        is_all_time_low = False
        product.consecutive_failures += 1
        product.last_error = result.error
        if product.status != "paused":
            if result.failure_kind == "extract":
                product.status = "unsupported"
            elif product.consecutive_failures >= _FAILURES_BEFORE_FAILED_STATUS:
                product.status = "failed"

    _schedule_next(product, result.ok, settings)
    session.add(log)
    await session.commit()

    if result.ok and result.data.price is not None:
        if old_price is not None and old_price > 0:
            try:
                notified = await notify_price_drop(
                    settings=settings,
                    product=product,
                    old_price=old_price,
                    new_price=result.data.price,
                    is_all_time_low=is_all_time_low,
                )
            except Exception:  
                logger.exception("Discord notification error for product %s", product.id)
    if not result.ok:
        logger.info("scrape failed product=%s: %s", product.id, result.error)
    result.notified = notified
    return result
