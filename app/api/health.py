from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_runtime
from app.db.models import Product
from app.db.session import get_session
from app.state import Runtime

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health(session: AsyncSession = Depends(get_session), rt: Runtime = Depends(get_runtime)):
    product_count = (await session.execute(select(func.count(Product.id)))).scalar_one()
    db_ok = product_count is not None
    ok = db_ok and rt.fetcher is not None
    return {
        "status": "ok" if ok else "degraded",
        "db": "ok" if db_ok else "error",
        "scheduler_running": rt.scheduler_running,
        "rss_running": rt.rss_running,
        "rss_fetched_at": rt.rss_fetched_at,
        "last_scrape_at": rt.last_scrape_at,
        "products": product_count,
    }
