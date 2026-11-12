from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth as auth_api
from app.api.auth import SESSION_COOKIE, expected_token
from app.api.adapters import router as adapters_router
from app.api.deals import router as deals_router
from app.api.health import router as health_router
from app.api.images import router as images_router
from app.api.notifications import router as notifications_router
from app.api.products import router as products_router
from app.api.settings import router as settings_router
from app.api.stores import router as stores_router
from app.config import get_settings
from app.db.session import dispose_engine, init_db
from app.rss.worker import rss_loop
from app.adapters_store import load_all_adapters
from app.scraping.browser import BrowserRenderer
from app.scraping.fetcher import Fetcher
from app.scheduler.worker import scheduler_loop
from app.images import ImageProxy
from app.state import runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pricetrack")

STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"

_OPEN_API_PATHS = {"/api/health", "/api/login", "/openapi.json", "/docs", "/redoc"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        settings = get_settings()
        path = request.url.path
        if (
            settings.admin_password
            and path.startswith("/api/")
            and path not in _OPEN_API_PATHS
            and request.cookies.get(SESSION_COOKIE) != expected_token(settings)
        ):
            return JSONResponse(status_code=401, content={"detail": "Wymagane logowanie"})
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    runtime.fetcher = Fetcher(settings)
    runtime.renderer = BrowserRenderer(settings)
    runtime.image_proxy = ImageProxy(settings)
    runtime.adapters = load_all_adapters()
    warmup_task: asyncio.Task | None = None
    if settings.playwright_enabled:
        warmup_task = asyncio.create_task(runtime.renderer.warmup(), name="browser-warmup")
    logger.info("loaded %d domain adapters", len(runtime.adapters))
    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(scheduler_loop(stop_event), name="scheduler"),
        asyncio.create_task(rss_loop(stop_event), name="rss"),
    ]
    yield
    stop_event.set()
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
    except TimeoutError:
        for task in tasks:
            task.cancel()
    if runtime.image_proxy is not None:
        await runtime.image_proxy.aclose()
        runtime.image_proxy = None
    if warmup_task is not None and not warmup_task.done():
        warmup_task.cancel()
    if runtime.renderer is not None:
        await runtime.renderer.aclose()
        runtime.renderer = None
    if runtime.fetcher is not None:
        await runtime.fetcher.aclose()
        runtime.fetcher = None
    await dispose_engine()


app = FastAPI(title="PriceTrack API", version="0.1.0", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.include_router(auth_api.router)
app.include_router(products_router)
app.include_router(deals_router)
app.include_router(notifications_router)
app.include_router(settings_router)
app.include_router(stores_router)
app.include_router(adapters_router)
app.include_router(health_router)
app.include_router(images_router)

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
else:
    @app.get("/")
    async def spa_missing():
        return PlainTextResponse(
            "Frontend is not built. Run: npm --prefix web install && npm --prefix web run build"
        )
