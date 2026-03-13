from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.market_data_models import ProviderStatus
from app.services.market_data_router import MarketDataRouter, get_default_market_data_router

router = APIRouter(prefix="/api/v1/market", tags=["market"])


def _get_router() -> MarketDataRouter:
    return get_default_market_data_router()


@router.get("/quote/{symbol}", response_model=dict)
async def get_quote(
    symbol: str,
    router_svc: MarketDataRouter = Depends(_get_router),
):
    try:
        quote = await router_svc.get_quote(symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return quote.model_dump()


@router.get("/bars/{symbol}", response_model=dict)
async def get_bars(
    symbol: str,
    interval: str = Query("1d", description="Resolution, e.g. 1m,5m,1d"),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    router_svc: MarketDataRouter = Depends(_get_router),
):
    if not start or not end:
        raise HTTPException(status_code=400, detail="start and end are required")
    try:
        bars = await router_svc.get_bars(symbol, interval, start, end)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "items": [b.model_dump() for b in bars],
    }


@router.get("/providers/status", response_model=dict)
async def providers_status(
    router_svc: MarketDataRouter = Depends(_get_router),
):
    # Lightweight health summary based on adapter status() methods.
    statuses: list[ProviderStatus] = []
    for name in ("alpaca", "free"):
        adapter = router_svc._get_adapter(name)  # type: ignore[attr-defined]
        if adapter is None:
            continue
        status = await adapter.status()
        statuses.append(status)
    return {"providers": [s.model_dump() for s in statuses]}

