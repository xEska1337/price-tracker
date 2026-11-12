from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters_store import (
    AdapterValidationError,
    delete_user_adapter,
    list_user_adapters,
    load_all_adapters,
    normalize_domain,
    parse_adapter_json,
    save_user_adapter,
    validate_adapter,
)
from app.api.products import _summary_one
from app.config import Settings, get_settings
from app.db.models import Product
from app.db.session import get_session
from app.scraping.adapters import Adapter, extract_via_adapter
from app.scraping.browser import BrowserUnavailable
from app.scraping.fetcher import FetchError
from app.scraping.prompt import build_adapter_prompt
from app.scraping.service import scrape_product
from app.state import runtime

router = APIRouter(prefix="/api", tags=["adapters"])


class AdapterInstallIn(BaseModel):
    product_id: str
    adapter: str = Field(min_length=2, max_length=20_000, description="Adapter JSON pasted from an LLM")


class AdapterInstallOut(BaseModel):
    domain: str
    price: float
    extractor: str
    product: dict


async def _load_page(url: str, settings: Settings) -> tuple[str, str]:
    if runtime.fetcher is not None:
        try:
            html, final_url, _status = await runtime.fetcher.get_text(url)
            return html, final_url
        except FetchError:
            pass
    renderer = runtime.renderer
    if renderer is not None and settings.playwright_enabled and await renderer.is_available():
        try:
            return await renderer.render(url)
        except BrowserUnavailable as exc:
            raise HTTPException(status_code=502, detail=f"Could not render the page: {exc}") from exc
        except Exception as exc:  
            raise HTTPException(
                status_code=502, detail=f"Could not load the page: {exc.__class__.__name__}"
            ) from exc
    raise HTTPException(
        status_code=502,
        detail="Could not load the page. Enable the headless browser fallback and try again.",
    )


async def _get_product(session: AsyncSession, product_id: str) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/adapters")
async def list_adapters():
    return {"user": list_user_adapters()}


@router.get("/adapters/{domain}")
async def get_adapter(domain: str, session: AsyncSession = Depends(get_session)):
    try:
        normalized = normalize_domain(domain)
    except AdapterValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for entry in list_user_adapters():
        if entry["domain"] == normalized:
            return {
                "domain": entry["domain"],
                "currency": entry["currency"],
                "selectors": entry["selectors"],
                "file": entry["file"],
            }
    raise HTTPException(status_code=404, detail="No user adapter for that domain")


@router.post("/products/{product_id}/adapter-prompt")
async def adapter_prompt(
    product_id: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    product = await _get_product(session, product_id)
    html, final_url = await _load_page(product.url, settings)
    prompt = build_adapter_prompt(final_url, html, product.domain)
    return {
        "domain": product.domain,
        "url": final_url,
        "prompt": prompt,
        "html_chars": len(html),
    }


@router.post("/adapters", response_model=AdapterInstallOut)
async def install_adapter(
    body: AdapterInstallIn,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    product = await _get_product(session, body.product_id)

    try:
        spec = parse_adapter_json(body.adapter)
        domain, clean = validate_adapter(spec, expected_domain=product.domain)
    except AdapterValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    html, final_url = await _load_page(product.url, settings)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    test_adapter = Adapter(domain=domain, selectors=clean["selectors"], currency=clean.get("currency"))
    extracted = extract_via_adapter(soup, test_adapter)
    if extracted is None or not extracted.has_price():
        detail = (
            "The adapter did not match a price on the page. Check the selectors against the page "
            "source and try again."
        )
        if extracted is not None:
            detail = (
                "The price selector matched an element, but its text could not be parsed as a price "
                f"({extracted.price}). Check that it targets the element containing the amount."
            )
        raise HTTPException(status_code=422, detail=detail)

    save_user_adapter(domain, clean)
    runtime.adapters = load_all_adapters()

    if runtime.fetcher is not None:
        await scrape_product(session, product, runtime.fetcher, settings, runtime.adapters, runtime.renderer)

    summary = await _summary_one(session, product)
    return AdapterInstallOut(
        domain=domain,
        price=float(extracted.price),
        extractor=extracted.extractor or f"adapter:{domain}",
        product=summary.model_dump(mode="json"),
    )


@router.delete("/adapters/{domain}", status_code=204)
async def remove_adapter(domain: str):
    try:
        normalized = normalize_domain(domain)
    except AdapterValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not delete_user_adapter(normalized):
        raise HTTPException(status_code=404, detail="No user adapter for that domain")
    runtime.adapters = load_all_adapters()
    return None
