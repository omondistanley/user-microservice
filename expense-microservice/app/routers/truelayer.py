"""TrueLayer (EU open banking): status and link/sync skeleton. Returns 503 when not configured."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.adapters.truelayer_adapter import TrueLayerAdapter, is_configured
from app.core.dependencies import get_current_user_id

router = APIRouter(prefix="/api/v1/truelayer", tags=["truelayer"])


class TrueLayerExchangeBody(BaseModel):
    code: str  # auth code from TrueLayer redirect


def _get_adapter() -> TrueLayerAdapter:
    return TrueLayerAdapter()


@router.get("/status")
async def truelayer_status():
    """Return whether TrueLayer is configured (for frontend provider check)."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="TrueLayer is not configured")
    return {"configured": True}


@router.post("/link-token")
async def truelayer_link_token(user_id: int = Depends(get_current_user_id)):
    """Return link/session URL for TrueLayer Connect. Skeleton: 503 when not configured."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="TrueLayer is not configured")
    adapter = _get_adapter()
    url = adapter.create_link_session(user_id)
    if not url:
        raise HTTPException(status_code=503, detail="TrueLayer link session not available")
    return {"link_url": url}


@router.post("/item")
async def truelayer_exchange(
    body: TrueLayerExchangeBody,
    user_id: int = Depends(get_current_user_id),
):
    """Exchange auth code for access; store item. Skeleton: 503 when not configured."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="TrueLayer is not configured")
    adapter = _get_adapter()
    result = adapter.exchange_public_token(user_id, body.code)
    if not result:
        raise HTTPException(status_code=503, detail="TrueLayer exchange not implemented")
    return result
