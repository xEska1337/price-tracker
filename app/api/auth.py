import hashlib
import hmac

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.api.schemas import LoginIn
from app.config import get_settings

router = APIRouter(tags=["auth"])

SESSION_COOKIE = "pt_session"
SESSION_MAX_AGE = 30 * 24 * 3600


def expected_token(settings) -> str:
    secret = settings.secret_key or hashlib.sha256(
        f"pricetrack-session:{settings.admin_password}".encode("utf-8")
    ).hexdigest()
    return hmac.new(secret.encode("utf-8"), b"pt-session-v1", hashlib.sha256).hexdigest()


@router.post("/api/login")
async def login(body: LoginIn, response: Response):
    settings = get_settings()
    if not settings.admin_password or not hmac.compare_digest(body.password, settings.admin_password):
        return JSONResponse(status_code=401, content={"detail": "Wrong password"})
    response.set_cookie(
        SESSION_COOKIE,
        expected_token(settings),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"ok": True}
