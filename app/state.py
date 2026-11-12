from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.scraping.adapters import Adapter
from app.scraping.browser import BrowserRenderer
from app.scraping.fetcher import Fetcher
from app.images import ImageProxy


@dataclass
class Runtime:
    fetcher: Fetcher | None = None
    renderer: BrowserRenderer | None = None
    image_proxy: ImageProxy | None = None
    adapters: list[Adapter] = field(default_factory=list)
    scheduler_running: bool = False
    rss_running: bool = False
    rss_fetched_at: datetime | None = None
    rss_last_new_count: int = 0
    last_scrape_at: datetime | None = None


runtime = Runtime()
