from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_session
from app.notifications.discord import send_test_message
from app.settings_store import effective_settings
from app.state import runtime

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def notification_status(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
):
    settings = await effective_settings(session, settings)
    return {
        "discord": {
            "enabled": bool(settings.discord_webhook_url),
            "min_drop_pct": settings.discord_min_drop_pct,
            "highlight_all_time_low": settings.discord_highlight_all_time_low,
        },
        "browser_fallback": {
            "enabled": settings.playwright_enabled,
            "available": bool(runtime.renderer and await runtime.renderer.is_available()),
            "reason": runtime.renderer.unavailable_reason if runtime.renderer else "not initialized",
        },
    }


@router.post("/test")
async def test_notification(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
):
    settings = await effective_settings(session, settings)
    if not settings.discord_webhook_url:
        raise HTTPException(
            status_code=400,
            detail="Discord webhook is not configured (set DISCORD_WEBHOOK_URL)",
        )
    sent = await send_test_message(settings)
    if not sent:
        raise HTTPException(status_code=502, detail="Discord rejected the test message")
    return {"sent": True}
