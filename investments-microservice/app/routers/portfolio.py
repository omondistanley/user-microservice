import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["portfolio"])
BARS_TIMEOUT = 8.0
GAINS_HISTORY_DAYS_MIN = 7
GAINS_HISTORY_DAYS_MAX = 365


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
    market_router: MarketDataRouter = Depends(_get_market_router),
):
    """Aggregate holdings; market value uses live quotes when available (same as sector breakdown)."""
    ds = _get_data_service()
    rows = ds.list_all_holdings_for_user(user_id)

    total_cost_basis = Decimal("0")
    for row in rows:
        quantity = Decimal(str(row.get("quantity") or "0"))
        avg_cost = Decimal(str(row.get("avg_cost") or "0"))
        total_cost_basis += quantity * avg_cost

    positions_with_value = await _build_positions_with_value(rows, market_router)
    value_by_symbol = {p["symbol"]: p["value"] for p in positions_with_value}

    total_market_value = sum((p["value"] for p in positions_with_value), Decimal("0"))

    positions: list[dict] = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        quantity = Decimal(str(row.get("quantity") or "0"))
        avg_cost = Decimal(str(row.get("avg_cost") or "0"))
        position_cost = quantity * avg_cost
        mv = value_by_symbol.get(symbol, position_cost)
        positions.append(
            {
                "symbol": row.get("symbol"),
                "quantity": quantity,
                "avg_cost": avg_cost,
                "currency": row.get("currency", "USD"),
                "cost_basis": position_cost,
                "market_value": mv,
            }
        )

    unrealized_pl = total_market_value - total_cost_basis

    return {
        "total_market_value": total_market_value,
        "total_cost_basis": total_cost_basis,
        "unrealized_pl": unrealized_pl,
        "positions": positions,
        "metadata": {
            "valuation_source": "quotes_with_cost_fallback",
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


@router.get("/portfolio/gains-history", response_model=dict)
async def gains_history(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
    days: int = Query(90, ge=GAINS_HISTORY_DAYS_MIN, le=GAINS_HISTORY_DAYS_MAX),
):
    """
    Gains/loss over time from current holdings and historical daily bars.
    Returns time series for total, manual-only, and alpaca-only. Assumes holdings (and quantities)
    were constant over the period; does not reflect past adds/sells.
    """
    rows = ds.list_all_holdings_for_user(user_id)
    if not rows:
        return {
            "dates": [],
            "series": {
                "total": {"value": [], "cost_basis": [], "gain_loss": []},
                "manual": {"value": [], "cost_basis": [], "gain_loss": []},
                "alpaca": {"value": [], "cost_basis": [], "gain_loss": []},
            },
            "note": "Add holdings to see gains over time.",
        }

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    symbols = list({(r.get("symbol") or "").strip().upper() for r in rows if (r.get("symbol") or "").strip()})

    symbol_to_dates: Dict[str, Dict[str, float]] = {}
    all_dates: set[str] = set()
    for symbol in symbols:
        try:
            bars = await asyncio.wait_for(
                market_router.get_bars(symbol, "1d", start_dt, end_dt),
                timeout=BARS_TIMEOUT,
            )
            if not bars:
                continue
            by_date: Dict[str, float] = {}
            for b in bars:
                ps = b.period_start
                dt = ps.date() if hasattr(ps, "date") else ps
                key = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
                by_date[key] = float(b.close)
                all_dates.add(key)
            symbol_to_dates[symbol] = by_date
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug("gains_history bars %s: %s", symbol, e)
            continue

    sorted_dates = sorted(all_dates)
    if not sorted_dates:
        return {
            "dates": [],
            "series": {
                "total": {"value": [], "cost_basis": [], "gain_loss": []},
                "manual": {"value": [], "cost_basis": [], "gain_loss": []},
                "alpaca": {"value": [], "cost_basis": [], "gain_loss": []},
            },
            "note": "No historical bar data available for the selected range.",
        }

    def close_for(sym: str, d: str) -> Optional[float]:
        by = symbol_to_dates.get(sym)
        if not by:
            return None
        if d in by:
            return by[d]
        idx = sorted_dates.index(d) if d in sorted_dates else -1
        for i in range(idx - 1, -1, -1):
            if sorted_dates[i] in by:
                return by[sorted_dates[i]]
        return None

    total_value: List[float] = []
    total_cost: List[float] = []
    total_gain: List[float] = []
    manual_value: List[float] = []
    manual_cost: List[float] = []
    manual_gain: List[float] = []
    alpaca_value: List[float] = []
    alpaca_cost: List[float] = []
    alpaca_gain: List[float] = []

    for d in sorted_dates:
        tv, tc = Decimal("0"), Decimal("0")
        mv, mc = Decimal("0"), Decimal("0")
        av, ac = Decimal("0"), Decimal("0")
        for r in rows:
            sym = (r.get("symbol") or "").strip().upper()
            qty = Decimal(str(r.get("quantity") or "0"))
            avg = Decimal(str(r.get("avg_cost") or "0"))
            cost = qty * avg
            close = close_for(sym, d)
            if close is not None:
                val = qty * Decimal(str(close))
            else:
                val = cost
            src = (r.get("source") or "manual").lower()
            tv += val
            tc += cost
            if src == "manual":
                mv += val
                mc += cost
            elif src == "alpaca":
                av += val
                ac += cost
        total_value.append(float(tv))
        total_cost.append(float(tc))
        total_gain.append(float(tv - tc))
        manual_value.append(float(mv))
        manual_cost.append(float(mc))
        manual_gain.append(float(mv - mc))
        alpaca_value.append(float(av))
        alpaca_cost.append(float(ac))
        alpaca_gain.append(float(av - ac))

    return {
        "dates": sorted_dates,
        "series": {
            "total": {"value": total_value, "cost_basis": total_cost, "gain_loss": total_gain},
            "manual": {"value": manual_value, "cost_basis": manual_cost, "gain_loss": manual_gain},
            "alpaca": {"value": alpaca_value, "cost_basis": alpaca_cost, "gain_loss": alpaca_gain},
        },
        "note": "Based on current holdings and historical prices.",
    }

