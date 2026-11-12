from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.config import Settings, get_settings
from app.images import ImageProxyError
from app.state import runtime

router = APIRouter(prefix="/api", tags=["images"])

CACHE_CONTROL = "public, max-age=604800"


@router.get("/image")
async def proxy_image(
    request: Request,
    url: str = Query(..., min_length=8, max_length=2048, description="Absolute http(s) image URL"),
    settings: Settings = Depends(get_settings),
):
    if not settings.image_proxy_enabled or runtime.image_proxy is None:
        if url.startswith(("http://", "https://")):
            return RedirectResponse(url, status_code=307, headers={"Cache-Control": "no-store"})
        raise HTTPException(status_code=400, detail="Only http and https image URLs are allowed")
    if request.headers.get("if-none-match"):
        pass
    try:
        data, content_type, etag = await runtime.image_proxy.fetch(url)
    except ImageProxyError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    headers = {
        "Cache-Control": CACHE_CONTROL,
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=data, media_type=content_type, headers=headers)
