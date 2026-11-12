from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings as get_env_settings
from app.db.models import AppSetting

SETTINGS_ROW_ID = 1


async def get_settings_row(session: AsyncSession, create: bool = False) -> AppSetting | None:
    row = await session.get(AppSetting, SETTINGS_ROW_ID)
    if row is None and create:
        row = AppSetting(id=SETTINGS_ROW_ID)
        session.add(row)
        await session.commit()
    return row


def apply_overrides(base: Settings, row: AppSetting | None) -> Settings:
    if row is None:
        return base
    updates: dict = {}
    if row.discord_webhook_url is not None:
        updates["discord_webhook_url"] = row.discord_webhook_url
    if row.discord_min_drop_pct is not None:
        updates["discord_min_drop_pct"] = row.discord_min_drop_pct
    if row.discord_highlight_all_time_low is not None:
        updates["discord_highlight_all_time_low"] = row.discord_highlight_all_time_low
    if row.playwright_enabled is not None:
        updates["playwright_enabled"] = row.playwright_enabled
    return base.model_copy(update=updates) if updates else base


async def effective_settings(session: AsyncSession, base: Settings | None = None) -> Settings:
    base = base or get_env_settings()
    row = await get_settings_row(session)
    return apply_overrides(base, row)


async def update_settings_row(
    session: AsyncSession,
    *,
    discord_webhook_url: str | None,
    discord_min_drop_pct: float | None,
    discord_highlight_all_time_low: bool | None,
    playwright_enabled: bool | None,
) -> AppSetting:
    row = await get_settings_row(session, create=True)
    assert row is not None
    row.discord_webhook_url = discord_webhook_url
    row.discord_min_drop_pct = discord_min_drop_pct
    row.discord_highlight_all_time_low = discord_highlight_all_time_low
    row.playwright_enabled = playwright_enabled
    await session.commit()
    return row
