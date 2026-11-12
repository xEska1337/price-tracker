from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_runtime
from app.api.schemas import (
    CreateProductIn,
    ManualPriceIn,
    PatchProductIn,
    ProductDetail,
    ProductSummary,
    RangeKey,
)
from app.config import RANGE_DAYS, Settings, get_settings
from app.db.models import PricePoint, Product, utcnow
from app.db.session import get_session
from app.scraping.normalize import domain_bucket, normalize_url
from app.scraping.service import scrape_product
from app.state import Runtime
from app.trends import (
    Point,
    compute_deltas,
    compute_stats,
    moving_average,
    sparkline_values,
)

router = APIRouter(prefix="/api/products", tags=["products"])


def _to_summary(product: Product, points: list[Point], now) -> ProductSummary:
    deltas = compute_deltas(points, now)
    return ProductSummary(
        id=product.id,
        url=product.url,
        domain=product.domain,
        title=product.title or product.url,
        image_url=product.image_url,
        currency=product.currency,
        last_price=product.last_price,
        last_price_at=product.last_price_at,
        interval=product.interval,
        status=product.status,
        last_error=product.last_error,
        delta_7d_pct=deltas["delta_7d_pct"],
        delta_30d_pct=deltas["delta_30d_pct"],
        sparkline=sparkline_values(points, now),
        last_checked_at=product.last_checked_at,
        next_check_at=product.next_check_at,
        created_at=product.created_at,
    )


async def _points_for(session: AsyncSession, product_ids: list[str]) -> dict[str, list[Point]]:
    if not product_ids:
        return {}
    rows = await session.execute(
        select(PricePoint.product_id, PricePoint.scraped_at, PricePoint.price)
        .where(PricePoint.product_id.in_(product_ids))
        .order_by(PricePoint.product_id, PricePoint.scraped_at)
    )
    grouped: dict[str, list[Point]] = defaultdict(list)
    for product_id, at, price in rows:
        grouped[product_id].append((at, price))
    return grouped


async def _summary_list(session: AsyncSession, products: list[Product]) -> list[ProductSummary]:
    now = utcnow()
    points = await _points_for(session, [p.id for p in products])
    return [_to_summary(p, points.get(p.id, []), now) for p in products]


async def _summary_one(session: AsyncSession, product: Product) -> ProductSummary:
    return (await _summary_list(session, [product]))[0]


async def _get_product(session: AsyncSession, product_id: str) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("", status_code=201)
async def create_product(
    body: CreateProductIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
    rt: Runtime = Depends(get_runtime),
    settings: Settings = Depends(get_settings),
):
    canonical = normalize_url(body.url)
    if not canonical:
        raise HTTPException(status_code=422, detail="Invalid URL")
    existing = (
        await session.execute(select(Product).where(Product.url_canonical == canonical))
    ).scalar_one_or_none()
    if existing is not None:
        response.status_code = 200  
        return await _summary_one(session, existing)

    product = Product(
        url=body.url.strip(),
        url_canonical=canonical,
        domain=domain_bucket(canonical),
        interval=body.interval,
        next_check_at=utcnow(),
    )
    session.add(product)
    await session.commit()

    if rt.fetcher is not None:
        await scrape_product(session, product, rt.fetcher, settings, rt.adapters, rt.renderer)
    return await _summary_one(session, product)


@router.get("")
async def list_products(session: AsyncSession = Depends(get_session)):
    products = (
        (await session.execute(select(Product).order_by(Product.created_at.desc()))).scalars().all()
    )
    return await _summary_list(session, list(products))


@router.get("/{product_id}")
async def get_product_detail(
    product_id: str,
    range: RangeKey = Query(default="30d"),
    session: AsyncSession = Depends(get_session),
):
    product = await _get_product(session, product_id)
    now = utcnow()
    rows = (
        await session.execute(
            select(PricePoint.scraped_at, PricePoint.price, PricePoint.in_stock)
            .where(PricePoint.product_id == product.id)
            .order_by(PricePoint.scraped_at)
        )
    ).all()
    all_points: list[Point] = [(at, price) for at, price, _ in rows]
    days = RANGE_DAYS[range]
    cutoff: datetime | None = None if days is None else now - timedelta(days=days)
    in_window = lambda at: cutoff is None or at >= cutoff
    avg_windowed = [(at, price) for at, price in moving_average(all_points, days=7) if in_window(at)]
    detail = _to_summary(product, all_points, now).model_dump()
    detail.update(
        {
            "range": range,
            "price_points": [
                {"at": at, "price": price, "in_stock": in_stock}
                for at, price, in_stock in rows
                if in_window(at)
            ],
            "moving_avg": [{"at": at, "price": price} for at, price in avg_windowed],
            "stats": compute_stats(all_points, now),
        }
    )
    return ProductDetail(**detail)


@router.patch("/{product_id}")
async def patch_product(
    product_id: str,
    body: PatchProductIn,
    session: AsyncSession = Depends(get_session),
):
    product = await _get_product(session, product_id)
    if body.interval is not None:
        product.interval = body.interval
        product.next_check_at = utcnow()
    if body.status is not None:
        product.status = body.status
        if body.status == "active":
            product.next_check_at = utcnow()
    await session.commit()
    return await _summary_one(session, product)


@router.post("/{product_id}/scrape")
async def scrape_now(
    product_id: str,
    session: AsyncSession = Depends(get_session),
    rt: Runtime = Depends(get_runtime),
    settings: Settings = Depends(get_settings),
):
    product = await _get_product(session, product_id)
    if rt.fetcher is None:
        raise HTTPException(status_code=503, detail="Scraper unavailable")
    await scrape_product(session, product, rt.fetcher, settings, rt.adapters, rt.renderer)
    return await _summary_one(session, product)


@router.post("/{product_id}/price")
async def add_manual_price(
    product_id: str,
    body: ManualPriceIn,
    session: AsyncSession = Depends(get_session),
):
    product = await _get_product(session, product_id)
    now = utcnow()
    session.add(PricePoint(product_id=product.id, price=round(body.price, 2), source="manual"))
    product.last_price = round(body.price, 2)
    product.last_price_at = now
    product.currency = product.currency or "PLN"
    product.consecutive_failures = 0
    await session.commit()
    return await _summary_one(session, product)


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: str, session: AsyncSession = Depends(get_session)):
    product = await _get_product(session, product_id)
    await session.delete(product)
    await session.commit()
    return Response(status_code=204)
