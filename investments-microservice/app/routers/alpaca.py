from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.core.dependencies import get_current_user_id
from app.services.alpaca_broker_client import create_order as alpaca_create_order
from app.services.alpaca_connection_service import AlpacaConnectionService
from app.services.holdings_data_service import HoldingsDataService


class AlpacaOrderCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=16)
    qty: Decimal = Field(..., gt=0)
    side: Literal["buy", "sell"] = "buy"
    type: Literal["market", "limit"] = "market"
    time_in_force: Literal["day", "gtc", "ioc", "fok"] = "day"
    limit_price: Optional[Decimal] = Field(None, ge=0)

router = APIRouter(prefix="/api/v1", tags=["alpaca"])

_DB_CONTEXT = {
    "host": DB_HOST or "localhost",
    "port": int(DB_PORT) if DB_PORT else 5432,
    "user": DB_USER or "postgres",
    "password": DB_PASSWORD or "postgres",
    "dbname": DB_NAME or "investments_db",
}


def _get_connection_service() -> AlpacaConnectionService:
    return AlpacaConnectionService(context=_DB_CONTEXT)


def _get_holdings_service() -> HoldingsDataService:
    return HoldingsDataService(context=_DB_CONTEXT)


@router.get("/alpaca/status", response_model=dict)
async def alpaca_status(
    user_id: int = Depends(get_current_user_id),
):
    svc = _get_connection_service()
    conn = svc.get_connection(user_id)
    if not conn:
        return {"connected": False}
    return {
        "connected": True,
        "alpaca_account_id": conn.get("alpaca_account_id"),
        "is_paper": conn.get("is_paper", True),
        "last_sync_at": conn.get("last_sync_at"),
    }


@router.post("/alpaca/link", response_model=dict)
async def alpaca_link(
    payload: dict,
    user_id: int = Depends(get_current_user_id),
):
    """
    Link an Alpaca account by storing API credentials.

    Expected payload shape:
    {
        "api_key_id": "...",
        "api_key_secret": "...",
        "alpaca_account_id": "...",   # optional
        "is_paper": true              # optional, default true
    }

    The API keys are stored encrypted when ENCRYPTION_KEY is configured.
    """
    api_key_id: Optional[str] = (payload.get("api_key_id") or "").strip() or None
    api_key_secret: Optional[str] = (payload.get("api_key_secret") or "").strip() or None
    alpaca_account_id: Optional[str] = (payload.get("alpaca_account_id") or "").strip() or None
    is_paper: bool = bool(payload.get("is_paper", True))

    if not api_key_id or not api_key_secret:
        raise HTTPException(status_code=400, detail="api_key_id and api_key_secret are required")

    svc = _get_connection_service()
    # For now we optimistically store credentials; a future enhancement can
    # validate them against Alpaca before saving.
    conn = svc.upsert_connection(
        user_id=user_id,
        api_key_id=api_key_id,
        api_key_secret=api_key_secret,
        alpaca_account_id=alpaca_account_id,
        is_paper=is_paper,
    )
    return {
        "connected": True,
        "alpaca_account_id": conn.get("alpaca_account_id"),
        "is_paper": conn.get("is_paper", True),
        "last_sync_at": conn.get("last_sync_at"),
    }


@router.delete("/alpaca/link", response_model=dict)
async def alpaca_unlink(
    user_id: int = Depends(get_current_user_id),
):
    """
    Disconnect the user's Alpaca account, remove stored credentials, and delete
    all holdings with source='alpaca' for this user.
    """
    holdings_svc = _get_holdings_service()
    holdings_svc.delete_holdings_by_source(user_id, "alpaca")
    conn_svc = _get_connection_service()
    deleted = conn_svc.delete_connection(user_id)
    return {"connected": False, "deleted": deleted}


@router.post("/alpaca/sync", response_model=dict)
async def alpaca_sync_trigger(
    user_id: int = Depends(get_current_user_id),
):
    """
    Trigger a one-off sync of Alpaca positions for the current user only.
    Fetches positions from Alpaca and replaces holdings with source='alpaca'.
    """
    from app.jobs.alpaca_sync import run_alpaca_sync_for_user
    result = run_alpaca_sync_for_user(user_id)
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return {"synced": result.get("synced", 0), "errors": result.get("errors", [])}


@router.post("/alpaca/orders", response_model=dict)
async def alpaca_place_order(
    payload: AlpacaOrderCreate,
    user_id: int = Depends(get_current_user_id),
):
    """
    Place a buy or sell order on Alpaca. Requires linked Alpaca account.
    """
    conn_svc = _get_connection_service()
    creds = conn_svc.get_credentials(user_id)
    if not creds:
        raise HTTPException(status_code=400, detail="Alpaca not connected. Link your account first.")
    if payload.type == "limit" and payload.limit_price is None:
        raise HTTPException(status_code=400, detail="limit_price required for limit orders")
    try:
        order = alpaca_create_order(
            api_key_id=creds["api_key_id"],
            api_key_secret=creds["api_key_secret"],
            is_paper=creds["is_paper"],
            symbol=payload.symbol.strip().upper(),
            qty=float(payload.qty),
            side=payload.side,
            order_type=payload.type,
            time_in_force=payload.time_in_force,
            limit_price=float(payload.limit_price) if payload.limit_price is not None else None,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "id": order.get("id"),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "type": order.get("type"),
        "status": order.get("status"),
        "filled_qty": order.get("filled_qty"),
        "qty": order.get("qty"),
    }

