from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.core.config import INTERNAL_API_KEY
from app.services.holdings_data_service import HoldingsDataService
from app.services.recommendation_data_service import RecommendationDataService
from app.services.recommendation_quality_service import build_quality_scorecard
from app.services.service_factory import ServiceFactory
from app.services.universe_bootstrap import run_bootstrap

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def _validate_internal_key(
    x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-Api-Key"),
):
    if INTERNAL_API_KEY and x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def _get_data_service() -> HoldingsDataService:
    ds = ServiceFactory.get_service("HoldingsDataService")
    if not isinstance(ds, HoldingsDataService):
        raise RuntimeError("HoldingsDataService not available")
    return ds


def _get_recommendation_data_service() -> RecommendationDataService:
    ds = ServiceFactory.get_service("RecommendationDataService")
    if not isinstance(ds, RecommendationDataService):
        raise RuntimeError("RecommendationDataService not available")
    return ds


@router.delete("/users/{user_id}/holdings", response_model=dict, include_in_schema=False)
async def purge_user_holdings(
    user_id: int,
    request: Request,
    _: None = Depends(_validate_internal_key),
):
    ds = _get_data_service()
    result = ds.purge_user_holdings(user_id)
    request_id = str(getattr(request.state, "request_id", "") or "")
    return {
        "user_id": user_id,
        "request_id": request_id or None,
        "deleted_count": result,
    }


@router.post("/universe/refresh", response_model=dict, include_in_schema=False)
async def refresh_universe(
    request: Request,
    limit: int = Query(500, ge=1, le=2000, description="Max symbols to fetch"),
    exchange: str = Query("US", description="Exchange code for symbol list"),
    use_alphavantage_fallback: bool = Query(True, description="Use Alpha Vantage when Finnhub profile missing"),
    _: None = Depends(_validate_internal_key),
):
    """Bootstrap security_universe from Finnhub (and optionally Alpha Vantage). Protected by X-Internal-Api-Key."""
    fetched, upserted, failed = await run_bootstrap(
        symbol_limit=limit,
        exchange=exchange,
        use_alphavantage_fallback=use_alphavantage_fallback,
    )
    request_id = str(getattr(request.state, "request_id", "") or "")
    return {
        "request_id": request_id or None,
        "symbols_fetched": fetched,
        "symbols_upserted": upserted,
        "symbols_failed": failed,
        "exchange": exchange,
    }


@router.get("/recommendations/quality-baseline", response_model=dict, include_in_schema=False)
async def recommendations_quality_baseline(
    user_id: int = Query(..., ge=1),
    runs_limit: int = Query(5, ge=2, le=20),
    _: None = Depends(_validate_internal_key),
):
    rec_svc = _get_recommendation_data_service()
    result = build_quality_scorecard(rec_svc, user_id=user_id, runs_limit=runs_limit)
    return {"user_id": user_id, **result}
