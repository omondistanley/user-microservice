import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user_id
from app.services.analyst_universe import get_security_info
from app.services.recommendation_data_service import RecommendationDataService
from app.services.recommendation_engine import RecommendationEngine
from app.services.service_factory import ServiceFactory
from app.services.market_data_router import MarketDataRouter, get_default_market_data_router
from app.services.news_router import get_news_for_symbol

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["recommendations"])

QUOTE_ENRICH_TIMEOUT = 3.0


def _get_engine() -> RecommendationEngine:
    return RecommendationEngine()


def _get_rec_data_service() -> RecommendationDataService:
    ds = ServiceFactory.get_service("RecommendationDataService")
    assert isinstance(ds, RecommendationDataService)
    return ds


def _get_market_router() -> MarketDataRouter:
    return get_default_market_data_router()


@router.post("/recommendations/run", response_model=dict)
async def run_recommendations(
    user_id: int = Depends(get_current_user_id),
    engine: RecommendationEngine = Depends(_get_engine),
) -> Dict[str, Any]:
    try:
        result = engine.run_for_user(user_id)
    except Exception as exc:
        msg = str(exc).strip() if str(exc).strip() else "Recommendation run failed. Ensure migrations (003) are applied."
        logger.exception("Recommendations run failed for user_id=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=msg)
    return result


BARS_ENRICH_TIMEOUT = 5.0


async def _fetch_quote_safe(router: MarketDataRouter, symbol: str) -> Optional[Dict[str, Any]]:
    """Return dict with last_price, price_as_of, change_pct (if available) or None on failure."""
    try:
        quote, _, _ = await asyncio.wait_for(
            router.get_quote_with_meta(symbol),
            timeout=QUOTE_ENRICH_TIMEOUT,
        )
        out: Dict[str, Any] = {
            "last_price": str(quote.price),
            "price_as_of": quote.as_of.isoformat() if quote.as_of else None,
        }
        if getattr(quote, "change_pct", None) is not None:
            out["change_pct"] = float(quote.change_pct)
        return out
    except Exception:
        return None


async def _fetch_bars_trend_safe(
    router: MarketDataRouter,
    symbol: str,
    end_dt: datetime,
    days: int = 30,
) -> Optional[float]:
    """Return 1M (or days) trend as decimal e.g. 0.05 for 5%, or None on failure."""
    try:
        start_dt = end_dt - timedelta(days=days)
        bars = await asyncio.wait_for(
            router.get_bars(symbol, "1d", start_dt, end_dt),
            timeout=BARS_ENRICH_TIMEOUT,
        )
        if not bars or len(bars) < 2:
            return None
        first_close = float(bars[0].close)
        last_close = float(bars[-1].close)
        if first_close and first_close > 0:
            return round((last_close - first_close) / first_close * 100, 2)
        return None
    except Exception:
        return None


@router.get("/recommendations/latest", response_model=dict)
async def latest_recommendations(
    user_id: int = Depends(get_current_user_id),
    rec_svc: RecommendationDataService = Depends(_get_rec_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
    enrich: bool = Query(False, description="Fetch live quotes for each symbol (slower)"),
) -> Dict[str, Any]:
    run = rec_svc.get_latest_run(user_id)
    if not run:
        return {"run": None, "items": []}
    items = rec_svc.list_items_for_run(run["run_id"])
    summary_items: List[Dict[str, Any]] = []
    for i in items:
        sym = i["symbol"]
        row: Dict[str, Any] = {
            "symbol": sym,
            "score": str(i["score"]),
            "confidence": str(i.get("confidence") or "0"),
        }
        sec = get_security_info(sym)
        if sec:
            row["sector"] = sec["sector"]
            row["full_name"] = sec["full_name"]
            row["description"] = sec["description"]
            row["asset_type"] = sec["asset_type"]
        summary_items.append(row)
    if enrich and summary_items:
        end_dt = datetime.now(timezone.utc)
        quote_tasks = [_fetch_quote_safe(market_router, it["symbol"]) for it in summary_items]
        bar_tasks = [
            _fetch_bars_trend_safe(market_router, it["symbol"], end_dt, 30)
            for it in summary_items
        ]
        quote_results, bar_results = await asyncio.gather(
            asyncio.gather(*quote_tasks, return_exceptions=True),
            asyncio.gather(*bar_tasks, return_exceptions=True),
        )
        for idx, res in enumerate(quote_results):
            if idx < len(summary_items) and isinstance(res, dict) and res:
                summary_items[idx]["last_price"] = res.get("last_price")
                summary_items[idx]["price_as_of"] = res.get("price_as_of")
                if res.get("change_pct") is not None:
                    summary_items[idx]["change_pct"] = res["change_pct"]
        for idx, trend in enumerate(bar_results):
            if idx < len(summary_items) and isinstance(trend, (int, float)):
                summary_items[idx]["trend_1m_pct"] = trend
    return {"run": run, "items": summary_items}


@router.get("/recommendations/{run_id}/explain", response_model=dict)
async def explain_recommendations(
    run_id: str,
    rec_svc: RecommendationDataService = Depends(_get_rec_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
    symbol: Optional[str] = Query(None, description="Enrich this symbol with live market data and trend"),
) -> Dict[str, Any]:
    try:
        rid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    items = rec_svc.list_items_for_run(rid)
    if not items:
        raise HTTPException(status_code=404, detail="Run not found or has no items")

    enrich_symbol = (symbol or "").strip().upper() or None
    end_dt = datetime.now(timezone.utc)
    start_30d = end_dt - timedelta(days=30)
    start_1y = end_dt - timedelta(days=365)

    out_items: List[Dict[str, Any]] = []
    for i in items:
        expl = dict(i.get("explanation_json") or {})
        sec = expl.get("security") or get_security_info(i["symbol"])
        if sec and not expl.get("security"):
            expl["security"] = sec
        elif not expl.get("security"):
            sym = i["symbol"]
            expl["security"] = {
                "full_name": sym,
                "sector": "—",
                "description": "",
                "asset_type": "unknown",
                "why_it_matters": "",
            }

        if enrich_symbol and (i.get("symbol") or "").upper() == enrich_symbol:
            try:
                quote, _, _ = await asyncio.wait_for(
                    market_router.get_quote_with_meta(enrich_symbol),
                    timeout=QUOTE_ENRICH_TIMEOUT,
                )
                expl["data_freshness"] = {
                    "provider": quote.provider,
                    "stale_seconds": quote.stale_seconds,
                }
                market: Dict[str, Any] = {
                    "current_price": str(quote.price),
                    "as_of": quote.as_of.isoformat() if quote.as_of else None,
                }
                bars_30d = await asyncio.wait_for(
                    market_router.get_bars(enrich_symbol, "1d", start_30d, end_dt),
                    timeout=BARS_ENRICH_TIMEOUT,
                )
                if bars_30d and len(bars_30d) >= 2:
                    first_close = float(bars_30d[0].close)
                    last_close = float(bars_30d[-1].close)
                    if first_close and first_close > 0:
                        trend_1m = (last_close - first_close) / first_close
                        market["trend_1m_pct"] = round(trend_1m * 100, 2)
                try:
                    bars_1y = await asyncio.wait_for(
                        market_router.get_bars(enrich_symbol, "1d", start_1y, end_dt),
                        timeout=BARS_ENRICH_TIMEOUT,
                    )
                    if bars_1y:
                        high_52w = max(float(b.high) for b in bars_1y)
                        low_52w = min(float(b.low) for b in bars_1y)
                        market["52w_high"] = round(high_52w, 2)
                        market["52w_low"] = round(low_52w, 2)
                except Exception:
                    pass
                expl["market"] = market
            except Exception:
                pass
            try:
                news_items = get_news_for_symbol(enrich_symbol, limit=5)
                if news_items:
                    recent = [{"title": n.get("title"), "url": n.get("url"), "published_at": n.get("published_at")} for n in news_items]
                    if expl.get("news_factors") is None:
                        expl["news_factors"] = {}
                    if not isinstance(expl["news_factors"], dict):
                        expl["news_factors"] = {}
                    expl["news_factors"]["recent_news"] = recent
                    if news_items and news_items[0].get("title"):
                        expl["analyst_note"] = (expl.get("analyst_note") or "") + " Latest: " + (news_items[0].get("title") or "")[:120]
            except Exception:
                pass

        out_items.append({
            "symbol": i["symbol"],
            "score": str(i["score"]),
            "confidence": str(i.get("confidence") or "0"),
            "explanation": expl,
        })

    return {"run_id": run_id, "items": out_items}

