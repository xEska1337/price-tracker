from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

IntervalKey = Literal["1h", "6h", "12h", "24h", "7d"]
RangeKey = Literal["7d", "30d", "90d", "all"]


class ProductSummary(BaseModel):
    id: str
    url: str
    domain: str
    title: str
    image_url: str | None
    currency: str | None
    last_price: float | None
    last_price_at: datetime | None
    interval: str
    status: str
    last_error: str | None
    delta_7d_pct: float | None
    delta_30d_pct: float | None
    sparkline: list[float]
    last_checked_at: datetime | None
    next_check_at: datetime | None
    created_at: datetime


class PricePointOut(BaseModel):
    at: datetime
    price: float
    in_stock: bool


class AvgPointOut(BaseModel):
    at: datetime
    price: float


class StatsOut(BaseModel):
    min: float | None
    max: float | None
    avg: float | None
    current: float | None
    at_all_time_low: bool
    delta_1d_pct: float | None
    delta_7d_pct: float | None
    delta_30d_pct: float | None


class ProductDetail(ProductSummary):
    range: str
    price_points: list[PricePointOut]
    moving_avg: list[AvgPointOut]
    stats: StatsOut


class CreateProductIn(BaseModel):
    url: str = Field(min_length=4, max_length=2048)
    interval: IntervalKey = "24h"


class PatchProductIn(BaseModel):
    interval: IntervalKey | None = None
    status: Literal["active", "paused"] | None = None


class ManualPriceIn(BaseModel):
    price: float = Field(gt=0, le=10_000_000)


class LoginIn(BaseModel):
    password: str


class DealOut(BaseModel):
    id: str
    title: str
    link: str
    image_url: str | None
    merchant: str | None
    price_raw: str | None
    category: str | None
    snippet: str | None
    published_at: datetime


class DealsResponse(BaseModel):
    fetched_at: datetime | None
    deals: list[DealOut]
