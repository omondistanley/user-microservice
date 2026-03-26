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
        hid = row.get("holding_id")
        positions.append(
            {
                "symbol": row.get("symbol"),
                "quantity": quantity,
                "avg_cost": avg_cost,
                "currency": row.get("currency", "USD"),
                "cost_basis": position_cost,
                "market_value": mv,
                "source": str(row.get("source") or "manual").lower(),
                "holding_id": str(hid) if hid is not None else None,
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


@router.get("/portfolio/health", response_model=dict)
async def portfolio_health(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
):
    """
    Composite portfolio health score (0-100) with tier, components, and flags.
    Not financial advice. For informational purposes only.
    """
    from app.services.portfolio_health_service import compute_health_score
    from app.services.sector_exposure_service import aggregate_by_sector

    rows = ds.list_all_holdings_for_user(user_id)
    if not rows:
        return {
            "score": 0,
            "tier": "amber",
            "headline": "Add holdings to calculate your portfolio health score",
            "components": {},
            "flags": [],
            "disclaimer": "Not financial advice. For informational purposes only.",
        }

    positions = await _build_positions_with_value(rows, market_router)
    context = _db_context()

    sector_data = aggregate_by_sector(context, positions)
    sector_breakdown: dict = {}
    for item in (sector_data.get("sectors") or []):
        name = item.get("sector") or item.get("name") or ""
        pct = float(item.get("weight") or item.get("pct") or 0)
        if name:
            sector_breakdown[name] = pct

    result = compute_health_score(
        user_id=user_id,
        positions=positions,
        sector_breakdown=sector_breakdown,
        db_context=context,
        save=True,
    )
    return result


@router.get("/portfolio/benchmark", response_model=dict)
async def portfolio_benchmark(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
    benchmark: str = Query("sp500", pattern="^(sp500|nasdaq|60_40|dividend)$"),
    days: int = Query(90, ge=7, le=365),
):
    """
    Compare portfolio TWR against a benchmark index over N days.
    Benchmarks: sp500 (SPY), nasdaq (QQQ), 60_40 (blend SPY+BND), dividend (VYM).
    Not financial advice. For informational purposes only.
    """
    _BENCHMARK_SYMBOLS = {
        "sp500": ["SPY"],
        "nasdaq": ["QQQ"],
        "60_40": ["SPY", "BND"],
        "dividend": ["VYM"],
    }
    _BENCHMARK_WEIGHTS = {
        "sp500": [1.0],
        "nasdaq": [1.0],
        "60_40": [0.6, 0.4],
        "dividend": [1.0],
    }
    _BENCHMARK_LABELS = {
        "sp500": "S&P 500 (SPY)",
        "nasdaq": "Nasdaq (QQQ)",
        "60_40": "60/40 Portfolio",
        "dividend": "Dividend (VYM)",
    }

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    symbols = _BENCHMARK_SYMBOLS[benchmark]
    weights = _BENCHMARK_WEIGHTS[benchmark]

    rows = ds.list_all_holdings_for_user(user_id)
    portfolio_symbols = list({(r.get("symbol") or "").strip().upper() for r in rows if (r.get("symbol") or "").strip()})

    # Fetch all bar data concurrently
    all_symbols = list(set(portfolio_symbols + symbols))
    bar_tasks = {sym: market_router.get_bars(sym, "1d", start_dt, end_dt) for sym in all_symbols}

    bars_by_symbol: Dict[str, Any] = {}
    for sym, task in bar_tasks.items():
        try:
            bars = await asyncio.wait_for(task, timeout=BARS_TIMEOUT)
            bars_by_symbol[sym] = bars or []
        except Exception:
            bars_by_symbol[sym] = []

    def twr_series(bar_list):
        """Return list of (date_str, cumulative_twr) from bars."""
        if not bar_list:
            return []
        result = []
        base = float(bar_list[0].close) if bar_list[0].close else None
        if not base or base == 0:
            return []
        for b in bar_list:
            ps = b.period_start
            dt_key = (ps.date() if hasattr(ps, "date") else ps).isoformat()
            twr = (float(b.close) - base) / base * 100
            result.append({"date": dt_key, "value": round(twr, 3)})
        return result

    # Portfolio TWR: equal-weight across held symbols (simplified)
    portfolio_series_list = [twr_series(bars_by_symbol.get(s, [])) for s in portfolio_symbols]
    portfolio_series_list = [s for s in portfolio_series_list if s]

    # Benchmark TWR: weighted blend
    bench_series_list = []
    for i, sym in enumerate(symbols):
        s = twr_series(bars_by_symbol.get(sym, []))
        w = weights[i]
        bench_series_list.append((s, w))

    # Build aligned date set
    all_dates: set = set()
    for s in portfolio_series_list:
        for pt in s:
            all_dates.add(pt["date"])
    sorted_dates = sorted(all_dates)

    def lookup(series, date_str):
        for pt in series:
            if pt["date"] == date_str:
                return pt["value"]
        return None

    portfolio_points = []
    benchmark_points = []
    for d in sorted_dates:
        # Portfolio: average of all held symbols
        p_vals = [lookup(s, d) for s in portfolio_series_list]
        p_vals = [v for v in p_vals if v is not None]
        p_avg = round(sum(p_vals) / len(p_vals), 3) if p_vals else None

        # Benchmark: weighted average
        b_val = 0.0
        b_weight_total = 0.0
        for (bs, bw) in bench_series_list:
            v = lookup(bs, d)
            if v is not None:
                b_val += v * bw
                b_weight_total += bw
        b_avg = round(b_val / b_weight_total, 3) if b_weight_total > 0 else None

        if p_avg is not None and b_avg is not None:
            portfolio_points.append({"date": d, "value": p_avg})
            benchmark_points.append({"date": d, "value": b_avg})

    # Alpha = last portfolio TWR - last benchmark TWR
    alpha = None
    if portfolio_points and benchmark_points:
        alpha = round(portfolio_points[-1]["value"] - benchmark_points[-1]["value"], 3)

    return {
        "benchmark": benchmark,
        "benchmark_label": _BENCHMARK_LABELS[benchmark],
        "days": days,
        "portfolio": portfolio_points,
        "benchmark_series": benchmark_points,
        "alpha_pct": alpha,
        "disclaimer": "Past performance does not guarantee future results. Returns shown are informational estimates only.",
    }


@router.get("/portfolio/etf-overlap", response_model=dict)
async def etf_overlap(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
):
    """
    Detect ETF double-exposure and ETF-to-ETF overlap.
    Informational only. Not financial advice.
    """
    from app.services.etf_overlap_service import calculate_etf_overlap, detect_cross_account_concentration
    rows = ds.list_all_holdings_for_user(user_id)
    positions = await _build_positions_with_value(rows, market_router)
    context = _db_context()
    warnings = calculate_etf_overlap(context, positions)

    # Build positions list for cross-account concentration (needs market_value and account_type)
    value_by_symbol = {p["symbol"]: float(p["value"]) for p in positions}
    cross_positions = [
        {
            "symbol": (r.get("symbol") or "").strip().upper(),
            "market_value": value_by_symbol.get((r.get("symbol") or "").strip().upper(), 0.0),
            "account_type": r.get("account_type") or "taxable",
        }
        for r in rows
    ]
    cross_account_warnings = detect_cross_account_concentration(cross_positions)

    return {
        "warnings": warnings,
        "count": len(warnings),
        "cross_account_warnings": cross_account_warnings,
        "disclaimer": "Overlap estimates are based on publicly available ETF holdings data. Constituent weights change frequently — this is an approximation.",
    }
