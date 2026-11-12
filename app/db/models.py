from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDatetime(TypeDecorator):

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    url: Mapped[str] = mapped_column(Text)
    url_canonical: Mapped[str] = mapped_column(Text, unique=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price_at: Mapped[datetime | None] = mapped_column(UTCDatetime, nullable=True)
    interval: Mapped[str] = mapped_column(String(4), default="24h")
    status: Mapped[str] = mapped_column(String(16), default="active")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDatetime, nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(UTCDatetime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDatetime, default=utcnow)

    price_points: Mapped[list[PricePoint]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )


class PricePoint(Base):
    __tablename__ = "price_points"

    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    scraped_at: Mapped[datetime] = mapped_column(
        UTCDatetime, primary_key=True, default=utcnow
    )
    price: Mapped[float] = mapped_column(Float)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(32), default="scrape")  

    product: Mapped[Product] = relationship(back_populates="price_points")


class RSSItem(Base):
    __tablename__ = "rss_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    external_id: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(UTCDatetime, index=True)
    fetched_at: Mapped[datetime] = mapped_column(UTCDatetime, default=utcnow)


class AppSetting(Base):

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    discord_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discord_min_drop_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    discord_highlight_all_time_low: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    playwright_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDatetime, default=utcnow)


class ScrapeLog(Base):
    __tablename__ = "scrape_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    at: Mapped[datetime] = mapped_column(UTCDatetime, default=utcnow)
    ok: Mapped[bool] = mapped_column(Boolean)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extractor: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
