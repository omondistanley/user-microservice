import asyncio
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
)
from app.core.dependencies import get_current_user_id
from app.services.holdings_data_service import HoldingsDataService
from app.services.sector_exposure_service import aggregate_by_sector
from app.services.look_through_service import get_look_through_exposure
from app.services.correlation_service import get_correlation_analysis
from app.services.stress_test_service import run_stress_test
from app.services.quality_score_service import get_quality_scores
from app.services.service_factory import ServiceFactory
from app.services.market_data_router import MarketDataRouter, get_default_market_data_router

router = APIRouter(prefix="/api/v1", tags=["portfolio"])


def _get_data_service() -> HoldingsDataService:
    ds = ServiceFactory.get_service("HoldingsDataService")
    if not isinstance(ds, HoldingsDataService):
        raise RuntimeError("HoldingsDataService not available")
    return ds


def _get_market_router() -> MarketDataRouter:
    return get_default_market_data_router()


def _db_context() -> Dict[str, Any]:
    return {
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "dbname": DB_NAME or "investments_db",
    }


@router.get("/portfolio/value", response_model=dict)
async def portfolio_value(
    user_id: int = Depends(get_current_user_id),
):
    """Aggregate holdings into a simple portfolio valuation snapshot.

    For now, market value is approximated using quantity * avg_cost for each
    position. This will be replaced by quote-driven valuation in later phases.
    """
    ds = _get_data_service()
    rows = ds.list_all_holdings_for_user(user_id)

    total_cost_basis = Decimal("0")
    total_market_value = Decimal("0")

    positions: list[dict] = []
    for row in rows:
        quantity = Decimal(str(row.get("quantity") or "0"))
        avg_cost = Decimal(str(row.get("avg_cost") or "0"))
        position_cost = quantity * avg_cost
        total_cost_basis += position_cost
        # Until real quotes exist, treat cost basis as a proxy for market value.
        total_market_value += position_cost
        positions.append(
            {
                "symbol": row.get("symbol"),
                "quantity": quantity,
                "avg_cost": avg_cost,
                "currency": row.get("currency", "USD"),
                "cost_basis": position_cost,
            }
        )

    unrealized_pl = total_market_value - total_cost_basis

    return {
        "total_market_value": total_market_value,
        "total_cost_basis": total_cost_basis,
        "unrealized_pl": unrealized_pl,
        "positions": positions,
        "metadata": {
            "valuation_source": "holdings_cost_basis",
        },
    }


@router.get("/portfolio/sector-breakdown", response_model=dict)
async def sector_breakdown(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
):
    """Portfolio-level sector weights and concentration warning (single sector > threshold)."""
    rows = ds.list_all_holdings_for_user(user_id)
    positions = await _build_positions_with_value(rows, market_router)
    context = _db_context()
    return aggregate_by_sector(context, positions)


async def _build_positions_with_value(
    rows: list,
    market_router: MarketDataRouter,
) -> list[dict]:
    """Build list of { symbol, quantity, value } using quote or avg_cost."""
    positions = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        quantity = Decimal(str(row.get("quantity") or "0"))
        avg_cost = Decimal(str(row.get("avg_cost") or "0"))
        value = quantity * avg_cost
        try:
            quote, _, _ = await asyncio.wait_for(
                market_router.get_quote_with_meta(symbol),
                timeout=5.0,
            )
            if quote and quote.price and quote.price > 0:
                value = quantity * quote.price
        except (asyncio.TimeoutError, Exception):
            pass
        positions.append({"symbol": symbol, "quantity": quantity, "value": value})
    return positions


@router.get("/portfolio/look-through", response_model=dict)
async def look_through(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
    include_sector: bool = True,
):
    """Underlying exposure after ETF look-through; optionally by sector."""
    rows = ds.list_all_holdings_for_user(user_id)
    positions = await _build_positions_with_value(rows, market_router)
    context = _db_context()
    return get_look_through_exposure(context, positions, include_sector=include_sector)


@router.get("/portfolio/correlation-matrix", response_model=dict)
async def correlation_matrix(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    days: int = 90,
):
    """Rolling correlation matrix of daily returns for held symbols; diversification score and high-correlation pairs."""
    rows = ds.list_all_holdings_for_user(user_id)
    symbols = list({(r.get("symbol") or "").strip().upper() for r in rows if (r.get("symbol") or "").strip()})
    context = _db_context()
    return get_correlation_analysis(context, symbols, days=days, backfill=True)


@router.get("/portfolio/stress-test", response_model=dict)
async def stress_test(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
):
    """Historical scenario stress test: projected return and $ impact per scenario (post look-through)."""
    rows = ds.list_all_holdings_for_user(user_id)
    positions = await _build_positions_with_value(rows, market_router)
    context = _db_context()
    look_through = get_look_through_exposure(context, positions, include_sector=True)
    by_sector = look_through.get("by_sector") or []
    total_value = look_through.get("total_value") or 0
    # Map by_sector items to { sector, value } for stress test
    positions_by_sector = [{"sector": s.get("name"), "value": s.get("value")} for s in by_sector]
    scenarios_result = run_stress_test(context, positions_by_sector, total_value)
    return {"total_value": total_value, "scenarios": scenarios_result}


@router.get("/portfolio/diversification-score", response_model=dict)
async def diversification_score(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    days: int = 90,
):
    """Diversification score (1 - avg |correlation|) and per-symbol marginal contribution."""
    rows = ds.list_all_holdings_for_user(user_id)
    symbols = list({(r.get("symbol") or "").strip().upper() for r in rows if (r.get("symbol") or "").strip()})
    context = _db_context()
    result = get_correlation_analysis(context, symbols, days=days, backfill=True)
    return {
        "diversification_score": result.get("diversification_score", 0),
        "per_symbol_marginal": result.get("per_symbol_marginal", {}),
        "symbols": result.get("symbols", []),
    }


@router.get("/portfolio/quality-scores", response_model=dict)
async def quality_scores(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
):
    """Per-holding quality score (1-10) and trend from fundamentals (valuation, profitability, health, growth)."""
    rows = ds.list_all_holdings_for_user(user_id)
    symbols = list({(r.get("symbol") or "").strip().upper() for r in rows if (r.get("symbol") or "").strip()})
    context = _db_context()
    scores = get_quality_scores(context, symbols)
    return {"quality_scores": scores}

