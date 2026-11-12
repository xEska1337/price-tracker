from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
from pathlib import Path
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


class BrowserUnavailable(RuntimeError):
    pass


class BrowserRenderer:

    def __init__(self, settings: Settings):
        self._settings = settings
        self._apply_browsers_path(settings)
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(1)
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._unavailable_reason: str | None = None

    @staticmethod
    def _apply_browsers_path(settings: Settings) -> None:
        if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
            return
        if settings.playwright_browsers_path:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = settings.playwright_browsers_path
            return
        for candidate in (
            Path.cwd() / ".playwright-browsers",
            Path(__file__).resolve().parents[2] / ".playwright-browsers",
        ):
            if candidate.is_dir():
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
                return

    def is_available_sync(self) -> bool:
        if self._unavailable_reason is not None:
            return False
        if importlib.util.find_spec("playwright") is None:
            self._unavailable_reason = "playwright is not installed"
            return False
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    async def is_available(self) -> bool:
        return self.is_available_sync()

    async def _ensure_browser(self) -> Any:
        if self._browser is not None:
            return self._browser
        async with self._lock:
            if self._browser is not None:
                return self._browser
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:  
                self._unavailable_reason = "playwright is not installed"
                raise BrowserUnavailable(self._unavailable_reason) from exc
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                )
            except Exception as exc:  
                self._unavailable_reason = f"could not launch Chromium: {exc}"
                await self._safe_close_locked()
                raise BrowserUnavailable(self._unavailable_reason) from exc
            logger.info("Playwright Chromium started for fallback scraping")
            return self._browser

    async def _ensure_context(self) -> Any:
        if self._context is not None:
            return self._context
        browser = await self._ensure_browser()
        settings = self._settings
        self._context = await browser.new_context(
            user_agent=settings.user_agent,
            locale="en-US",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9,pl;q=0.8"},
        )
        self._context.set_default_timeout(settings.playwright_timeout_ms)
        return self._context

    async def warmup(self) -> bool:
        if not await self.is_available():
            return False
        try:
            context = await self._ensure_context()
            page = await context.new_page()
            await page.goto("about:blank")
            await page.close()
            logger.info("Playwright Chromium warmed up")
            return True
        except BrowserUnavailable:
            return False
        except Exception as exc:
            logger.warning("Playwright warmup failed: %s", exc)
            return False

    async def _safe_close_locked(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
        except Exception:  
            pass
        self._context = None
        try:
            if self._browser is not None:
                await self._browser.close()
        except Exception:  
            pass
        self._browser = None
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:  
            pass
        self._playwright = None

    async def render(self, url: str) -> tuple[str, str]:
        if not await self.is_available():
            raise BrowserUnavailable(self._unavailable_reason or "browser unavailable")
        settings = self._settings
        async with self._semaphore:
            context = await self._ensure_context()
            page = await context.new_page()
            try:
                await page.goto(
                    url,
                    wait_until=settings.playwright_navigation_wait,
                    timeout=settings.playwright_timeout_ms,
                )
                try:
                    await page.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    pass  
                if settings.playwright_settle_ms > 0:
                    await page.wait_for_timeout(settings.playwright_settle_ms)
                html = await page.content()
                final_url = page.url
            finally:
                await page.close()
        return html, final_url

    async def aclose(self) -> None:
        async with self._lock:
            await self._safe_close_locked()
