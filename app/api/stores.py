from fastapi import APIRouter

from app.stores import stores_payload

router = APIRouter(prefix="/api/stores", tags=["stores"])


@router.get("")
async def list_stores():
    return stores_payload()
