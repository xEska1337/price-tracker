from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_session
from app.settings_store import apply_overrides, get_settings_row, update_settings_row
from app.state import runtime

router = APIRouter(prefix="/api/settings", tags=["settings"])

WEBHOOK_RE = re.compile(r"^https://(?:discord\.com|discordapp\.com)/api/webhooks/\d+/[\w-]+$")


class DiscordSettingsIn(BaseModel):
    webhook_url: str | None = Field(default=None, max_length=500)
    min_drop_pct: float | None = Field(default=None, ge=0, le=100)
    highlight_all_time_low: bool | None = None


class SettingsIn(BaseModel):
    discord: DiscordSettingsIn | None = None
    playwright_enabled: bool | None = None


def _browser_status(settings: Settings) -> dict:
    renderer = runtime.renderer
    return {
        "enabled": settings.playwright_enabled,
        "available": bool(renderer and renderer.is_available_sync()),
        "reason": renderer.unavailable_reason if renderer else "not initialized",
    }


def _payload(settings: Settings) -> dict:
    return {
        "discord": {
            "webhook_url": settings.discord_webhook_url or "",
            "configured": bool(settings.discord_webhook_url),
            "min_drop_pct": settings.discord_min_drop_pct,
            "highlight_all_time_low": settings.discord_highlight_all_time_low,
        },
        "browser": _browser_status(settings),
    }


@router.get("")
async def get_app_settings(
    session: AsyncSession = Depends(get_session),
    base: Settings = Depends(get_settings),
):
    row = await get_settings_row(session)
    return _payload(apply_overrides(base, row))


@router.put("")
async def put_app_settings(
    body: SettingsIn,
    session: AsyncSession = Depends(get_session),
    base: Settings = Depends(get_settings),
):
    current = apply_overrides(base, await get_settings_row(session))
    discord = body.discord

    webhook = current.discord_webhook_url
    min_drop = current.discord_min_drop_pct
    highlight = current.discord_highlight_all_time_low
    if discord is not None:
        if discord.webhook_url is not None:
            webhook = discord.webhook_url.strip()
            if webhook and not WEBHOOK_RE.match(webhook):
                raise HTTPException(
                    status_code=422,
                    detail="That does not look like a Discord webhook URL "
                    "(expected https://discord.com/api/webhooks/<id>/<token>)",
                )
        if discord.min_drop_pct is not None:
            min_drop = discord.min_drop_pct
        if discord.highlight_all_time_low is not None:
            highlight = discord.highlight_all_time_low
    playwright = body.playwright_enabled if body.playwright_enabled is not None else current.playwright_enabled

    row = await update_settings_row(
        session,
        discord_webhook_url=webhook,
        discord_min_drop_pct=min_drop,
        discord_highlight_all_time_low=highlight,
        playwright_enabled=playwright,
    )
    return _payload(apply_overrides(base, row))
