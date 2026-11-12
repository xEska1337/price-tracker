from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DealOut, DealsResponse
from app.db.models import RSSItem
from app.db.session import get_session
from app.rss import worker as rss_worker
from app.state import runtime

router = APIRouter(prefix="/api/deals", tags=["deals"])


@router.get("", response_model=DealsResponse)
async def list_deals(session: AsyncSession = Depends(get_session)):
    items = (
        (await session.execute(select(RSSItem).order_by(RSSItem.published_at.desc()).limit(100)))
        .scalars()
        .all()
    )
    return DealsResponse(
        fetched_at=runtime.rss_fetched_at,
        deals=[
            DealOut(
                id=item.id,
                title=item.title,
                link=item.link,
                image_url=item.image_url,
                merchant=item.merchant,
                price_raw=item.price_raw,
                category=item.category,
                snippet=item.snippet,
                published_at=item.published_at,
            )
            for item in items
        ],
    )


@router.post("/refresh")
async def refresh_deals():
    new_count = await rss_worker.fetch_and_store()
    if new_count < 0:
        raise HTTPException(status_code=502, detail="Could not fetch the RSS feed")
    return {"count": new_count, "fetched_at": runtime.rss_fetched_at}
