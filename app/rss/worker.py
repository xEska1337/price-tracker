from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select

from app.config import get_settings
from app.db.models import RSSItem, utcnow
from app.db.session import get_session_factory
from app.rss.parse import parse_feed
from app.scraping.fetcher import FetchError
from app.state import runtime

logger = logging.getLogger(__name__)


async def fetch_and_store() -> int:
    settings = get_settings()
    if runtime.fetcher is None:
        return -1
    try:
        payload = await runtime.fetcher.get_bytes(settings.rss_url)
    except FetchError as exc:
        logger.warning("RSS fetch failed: %s", exc)
        return -1
    items = parse_feed(payload)
    now = utcnow()
    factory = get_session_factory()
    new_count = 0
    async with factory() as session:
        external_ids = {item["external_id"] for item in items}
        existing = set(
            (
                await session.execute(
                    select(RSSItem.external_id).where(RSSItem.external_id.in_(external_ids))
                )
            ).scalars()
        )
        for item in items:
            if item["external_id"] in existing:
                continue
            session.add(RSSItem(**item))
            new_count += 1
        cutoff = now - timedelta(hours=settings.rss_keep_hours)
        await session.execute(delete(RSSItem).where(RSSItem.published_at < cutoff))
        over_limit_ids = (
            await session.execute(
                select(RSSItem.id)
                .order_by(RSSItem.published_at.desc())
                .offset(settings.rss_max_items)
            )
        ).scalars().all()
        if over_limit_ids:
            await session.execute(delete(RSSItem).where(RSSItem.id.in_(over_limit_ids)))
        await session.commit()
    runtime.rss_fetched_at = now
    runtime.rss_last_new_count = new_count
    logger.info("RSS refresh: %s new of %s items", new_count, len(items))
    return new_count


async def rss_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    runtime.rss_running = True
    while not stop_event.is_set():
        try:
            await fetch_and_store()
        except Exception:
            logger.exception("RSS iteration failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.rss_poll_seconds)
        except TimeoutError:
            pass
    runtime.rss_running = False
