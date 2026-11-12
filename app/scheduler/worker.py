from __future__ import annotations

import asyncio
import logging

from sqlalchemy import or_, select

from app.config import get_settings
from app.db.models import Product, utcnow
from app.db.session import get_session_factory
from app.scraping.service import scrape_product
from app.state import runtime

logger = logging.getLogger(__name__)


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    factory = get_session_factory()
    runtime.scheduler_running = True
    logger.info("scheduler loop started (poll=%ss)", settings.scrape_poll_seconds)
    while not stop_event.is_set():
        try:
            async with factory() as session:
                now = utcnow()
                stmt = (
                    select(Product)
                    .where(
                        Product.status.in_(("active", "failed", "unsupported")),
                        or_(Product.next_check_at.is_(None), Product.next_check_at <= now),
                    )
                    .order_by(Product.next_check_at)
                    .limit(settings.scrape_batch_size)
                )
                products = (await session.execute(stmt)).scalars().all()
                for product in products:
                    if stop_event.is_set():
                        break
                    await scrape_product(
                        session, product, runtime.fetcher, settings,
                        runtime.adapters, runtime.renderer,
                    )
                    runtime.last_scrape_at = utcnow()
        except Exception:
            logger.exception("scheduler iteration failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.scrape_poll_seconds)
        except TimeoutError:
            pass
    runtime.scheduler_running = False
    logger.info("scheduler loop stopped")
