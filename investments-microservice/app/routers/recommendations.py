import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.core.rate_limit import rate_limit_dep

from app.core.config import (
    ALPHAVANTAGE_API_KEY,
    BENZINGA_API_KEY,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    FINNHUB_API_KEY,
    NEWS_PROVIDER_ORDER,
    RECOMMENDATIONS_PAGE_SIZE,
    RECOMMENDATIONS_EXPLAIN_CACHE_TTL_SECONDS,
    RECOMMENDATIONS_NEWS_CACHE_TTL_SECONDS,
    RECOMMENDATIONS_SENTIMENT_CACHE_TTL_SECONDS,
    SENTIMENT_LOOKBACK_DAYS,
)
from app.core.dependencies import get_current_user_id
from app.services.analyst_universe import get_security_info
from app.services.finance_context_client import fetch_finance_context
from app.services.recommendation_data_service import RecommendationDataService
from app.services.recommendation_engine import RecommendationEngine
from app.services.recommendation_evidence import augment_explanation_for_detail
from app.services.risk_profile_service import RiskProfileDataService
from app.services.service_factory import ServiceFactory
from app.services.market_data_router import MarketDataRouter, get_default_market_data_router
from app.services.news_router import get_news_for_symbol
from app.services.sentiment_service import get_sentiment_trend_and_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["recommendations"])

QUOTE_ENRICH_TIMEOUT = 3.0
_EXPLAIN_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_NEWS_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_SENTIMENT_CACHE: Dict[str, Tuple[float, Tuple[List[Dict[str, Any]], Optional[float], str]]] = {}


def _get_engine() -> RecommendationEngine:
    return RecommendationEngine()


def _get_rec_data_service() -> RecommendationDataService:
    ds = ServiceFactory.get_service("RecommendationDataService")
    assert isinstance(ds, RecommendationDataService)
    return ds


def _get_risk_profile_service() -> RiskProfileDataService:
    svc = ServiceFactory.get_service("RiskProfileDataService")
    assert isinstance(svc, RiskProfileDataService)
    return svc


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


def _configured_news_providers() -> Dict[str, bool]:
    """
    Headline/news integrations only. TwelveData is used for market quotes/bars, not the news router.
    Alpha Vantage key is shown for parity with NEWS_PROVIDER_ORDER; wire-up in news_router is optional.
    """
    return {
        "benzinga": bool((BENZINGA_API_KEY or "").strip()),
        "finnhub": bool((FINNHUB_API_KEY or "").strip()),
        "alphavantage": bool((ALPHAVANTAGE_API_KEY or "").strip()),
    }


@router.post("/recommendations/run", response_model=dict)
async def run_recommendations(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    engine: RecommendationEngine = Depends(_get_engine),
    _rate: None = Depends(rate_limit_dep(requests_per_minute=10)),
) -> Dict[str, Any]:
    auth_header = request.headers.get("Authorization") if request else None
    try:
        result = engine.run_for_user(user_id, auth_header=auth_header)
    except Exception as exc:
        msg = str(exc).strip() if str(exc).strip() else (
            "Recommendation run failed. Ensure DB migrations are applied "
            "(including 013_risk_profile_use_finance_data for personalized finance toggles)."
        )
        logger.exception("Recommendations run failed for user_id=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=msg)
    items = result.get("items") if isinstance(result, dict) else []
    try:
        score_vals = [float(i.get("score") or 0.0) for i in (items or []) if isinstance(i, dict)]
        conf_vals = [float(i.get("confidence") or 0.0) for i in (items or []) if isinstance(i, dict)]
        logger.info(
            "recommendation_run_quality_baseline user_id=%s items=%s avg_score=%.4f avg_confidence=%.4f",
            user_id,
            len(score_vals),
            (sum(score_vals) / len(score_vals)) if score_vals else 0.0,
            (sum(conf_vals) / len(conf_vals)) if conf_vals else 0.0,
        )
    except Exception:
        pass
    return result


BARS_ENRICH_TIMEOUT = 5.0


async def _enrich_explanation_for_symbol(
    expl: Dict[str, Any],
    enrich_sym: str,
    market_router: MarketDataRouter,
    end_dt: datetime,
    start_30d: datetime,
    start_1y: datetime,
) -> None:
    """Attach market, enrichment, news, and sentiment blocks for one ticker (mutates expl)."""
    if not enrich_sym:
        return

    # Initialize presence keys so the frontend can render placeholders consistently.
    providers = [p.strip().lower() for p in (NEWS_PROVIDER_ORDER or "").split(",") if p.strip()]
    conf = _configured_news_providers()
    expl.setdefault("data_freshness", {"provider": "Unavailable", "stale_seconds": None})
    expl.setdefault("market", {})
    expl.setdefault("enrichment", {"data_freshness": expl["data_freshness"]})
    expl.setdefault("news_factors", {"recent_news": []})
    expl.setdefault("sentiment_trend_7d", {"daily_scores": [], "rolling_avg_7d": None})
    expl.setdefault(
        "news_provider_status",
        {
            "provider_order": providers,
            "configured_keys": conf,
            "message": "Unavailable",
        },
    )

    # 1) Market quote + trend (best effort)
    try:
        quote, _, _ = await asyncio.wait_for(
            market_router.get_quote_with_meta(enrich_sym),
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
        if getattr(quote, "change_pct", None) is not None:
            market["change_pct"] = float(quote.change_pct)

        # 30d trend
        try:
            bars_30d = await asyncio.wait_for(
                market_router.get_bars(enrich_sym, "1d", start_30d, end_dt),
                timeout=BARS_ENRICH_TIMEOUT,
            )
            if bars_30d and len(bars_30d) >= 2:
                first_close = float(bars_30d[0].close)
                last_close = float(bars_30d[-1].close)
                if first_close and first_close > 0:
                    trend_1m = (last_close - first_close) / first_close
                    market["trend_1m_pct"] = round(trend_1m * 100, 2)
        except Exception:
            pass

        # 52w range
        try:
            bars_1y = await asyncio.wait_for(
                market_router.get_bars(enrich_sym, "1d", start_1y, end_dt),
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
        expl["enrichment"] = {
            "quote": {
                "price": str(quote.price),
                "as_of": quote.as_of.isoformat() if quote.as_of else None,
                "change_pct": float(quote.change_pct)
                if getattr(quote, "change_pct", None) is not None
                else None,
            },
            "trend_1m_pct": market.get("trend_1m_pct"),
            "52w_high": market.get("52w_high"),
            "52w_low": market.get("52w_low"),
            "data_freshness": expl["data_freshness"],
        }
    except Exception as exc:
        # Keep initialized defaults; optionally record error for observability.
        expl["data_freshness"] = {
            "provider": "Unavailable",
            "stale_seconds": None,
            "error": str(exc),
        }
        if isinstance(expl.get("enrichment"), dict):
            expl["enrichment"]["data_freshness"] = expl["data_freshness"]

    # 2) News (best effort + diagnostics)
    try:
        news_key = enrich_sym.upper()
        now_ts = time.monotonic()
        cached_news = _NEWS_CACHE.get(news_key)
        if (
            cached_news
            and RECOMMENDATIONS_NEWS_CACHE_TTL_SECONDS > 0
            and now_ts - cached_news[0] <= RECOMMENDATIONS_NEWS_CACHE_TTL_SECONDS
        ):
            news_items = cached_news[1]
        else:
            news_items = get_news_for_symbol(enrich_sym, limit=5)
            _NEWS_CACHE[news_key] = (now_ts, news_items or [])
        recent: List[Dict[str, Any]] = []
        if news_items:
            recent = [
                {
                    "title": n.get("title"),
                    "url": n.get("url"),
                    "published_at": n.get("published_at"),
                    "source_provider": n.get("source_provider") or "news",
                }
                for n in news_items
            ]
        expl["news_factors"] = {"recent_news": recent}
        if isinstance(expl.get("enrichment"), dict):
            expl["enrichment"]["recent_news"] = recent

        if recent:
            expl["news_provider_status"] = {
                "provider_order": providers,
                "configured_keys": conf,
                "message": f"Fetched {len(recent)} headlines for this symbol.",
            }
        else:
            expl["news_provider_status"] = {
                "provider_order": providers,
                "configured_keys": conf,
                "message": "No headlines returned in current window for this symbol.",
            }
    except Exception as exc:
        expl["news_factors"] = {"recent_news": []}
        if isinstance(expl.get("enrichment"), dict):
            expl["enrichment"]["recent_news"] = []
        expl["news_provider_status"] = {
            "provider_order": providers,
            "configured_keys": conf,
            "message": "News fetch failed for this symbol.",
            "error": str(exc),
        }

    # 3) Sentiment trend (best effort)
    try:
        ctx = _db_context()
        today = date(end_dt.year, end_dt.month, end_dt.day)
        sent_key = f"{enrich_sym.upper()}:{today.isoformat()}:{SENTIMENT_LOOKBACK_DAYS}"
        now_ts = time.monotonic()
        cached_sent = _SENTIMENT_CACHE.get(sent_key)
        if (
            cached_sent
            and RECOMMENDATIONS_SENTIMENT_CACHE_TTL_SECONDS > 0
            and now_ts - cached_sent[0] <= RECOMMENDATIONS_SENTIMENT_CACHE_TTL_SECONDS
        ):
            daily_scores, rolling_avg, summary_str = cached_sent[1]
        else:
            daily_scores, rolling_avg, summary_str = get_sentiment_trend_and_summary(
                ctx, enrich_sym, today, SENTIMENT_LOOKBACK_DAYS
            )
            _SENTIMENT_CACHE[sent_key] = (now_ts, (daily_scores, rolling_avg, summary_str))
        expl["sentiment_trend_7d"] = {
            "daily_scores": list(daily_scores),
            "rolling_avg_7d": rolling_avg,
        }
        if summary_str:
            expl["sentiment_summary"] = summary_str
    except Exception as exc:
        expl["sentiment_trend_7d"] = {"daily_scores": [], "rolling_avg_7d": None, "error": str(exc)}


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


def _build_pagination_links(
    page: int, page_size: int, total_pages: int
) -> Dict[str, Optional[str]]:
    """Build HATEOAS _links for list; query part only (client appends to path)."""
    base = f"page={page}&page_size={page_size}"
    links: Dict[str, Optional[str]] = {
        "self": f"?page={page}&page_size={page_size}",
        "first": "?page=1&page_size={}".format(page_size),
        "last": f"?page={total_pages}&page_size={page_size}" if total_pages >= 1 else None,
        "prev": f"?page={page - 1}&page_size={page_size}" if page > 1 else None,
        "next": f"?page={page + 1}&page_size={page_size}" if page < total_pages else None,
    }
    return links


@router.get("/recommendations/latest", response_model=dict)
async def latest_recommendations(
    user_id: int = Depends(get_current_user_id),
    rec_svc: RecommendationDataService = Depends(_get_rec_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(RECOMMENDATIONS_PAGE_SIZE, ge=1, le=100, description="Items per page"),
    enrich: bool = Query(False, description="Fetch live quotes for current page (slower)"),
) -> Dict[str, Any]:
    run = rec_svc.get_latest_run(user_id)
    if not run:
        return {
            "run": None,
            "items": [],
            "pagination": {"page": 1, "page_size": page_size, "total_items": 0, "total_pages": 0},
            "_links": _build_pagination_links(1, page_size, 0),
        }
    items, total_items = rec_svc.list_items_for_run_paginated(
        run["run_id"], limit=page_size, offset=(page - 1) * page_size
    )
    total_pages = (total_items + page_size - 1) // page_size if page_size else 0

    summary_items: List[Dict[str, Any]] = []
    for i in items:
        sym = i["symbol"]
        try:
            score_val = float(i["score"])
            score_str = f"{score_val:.2f}"
        except (TypeError, ValueError):
            score_str = str(i["score"])
        try:
            conf_val = float(i.get("confidence") or "0")
            conf_str = f"{conf_val:.2f}"
        except (TypeError, ValueError):
            conf_str = str(i.get("confidence") or "0")
        row: Dict[str, Any] = {
            "symbol": sym,
            "score": score_str,
            "confidence": conf_str,
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

    portfolio = None
    ps = run.get("portfolio_snapshot") if isinstance(run, dict) else None
    if isinstance(ps, dict):
        portfolio = ps

    return {
        "run": run,
        "items": summary_items,
        "portfolio": portfolio,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
        },
        "_links": _build_pagination_links(page, page_size, total_pages),
    }


@router.get("/recommendations/{run_id}/explain", response_model=dict)
async def explain_recommendations(
    request: Request,
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    rec_svc: RecommendationDataService = Depends(_get_rec_data_service),
    risk_svc: RiskProfileDataService = Depends(_get_risk_profile_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
    symbol: Optional[str] = Query(None, description="Enrich this symbol with live market data and trend"),
) -> Dict[str, Any]:
    try:
        rid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    run_row = rec_svc.get_run_for_user(rid, user_id)
    if not run_row:
        raise HTTPException(status_code=404, detail="Run not found")
    items = rec_svc.list_items_for_run(rid)
    if not items:
        raise HTTPException(status_code=404, detail="Run not found or has no items")

    risk = risk_svc.get_risk_profile(user_id) or {}
    auth_header = request.headers.get("Authorization") if request else None
    finance_ctx = None
    if risk.get("use_finance_data_for_recommendations") and auth_header:
        try:
            finance_ctx = fetch_finance_context(auth_header)
        except Exception:
            finance_ctx = None

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

        sym_u = (i.get("symbol") or "").strip().upper()
        # Enrich each row with live market + news + sentiment for that symbol (query param optional filter).
        if sym_u and (not enrich_symbol or sym_u == enrich_symbol):
            await _enrich_explanation_for_symbol(
                expl,
                sym_u,
                market_router,
                end_dt,
                start_30d,
                start_1y,
            )
            augment_explanation_for_detail(expl, risk, finance_ctx, sym_u)

        try:
            out_score = f"{float(i['score']):.2f}"
        except (TypeError, ValueError):
            out_score = str(i["score"])
        try:
            out_conf = f"{float(i.get('confidence') or 0):.2f}"
        except (TypeError, ValueError):
            out_conf = str(i.get("confidence") or "0")
        out_items.append({
            "symbol": i["symbol"],
            "score": out_score,
            "confidence": out_conf,
            "explanation": expl,
        })

    return {"run_id": run_id, "items": out_items}


@router.get("/recommendations/{run_id}/explain/{symbol}", response_model=dict)
async def explain_recommendation_symbol(
    request: Request,
    run_id: str,
    symbol: str,
    user_id: int = Depends(get_current_user_id),
    rec_svc: RecommendationDataService = Depends(_get_rec_data_service),
    risk_svc: RiskProfileDataService = Depends(_get_risk_profile_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
) -> Dict[str, Any]:
    try:
        rid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    cache_key = f"{user_id}:{run_id}:{sym}"
    now_ts = time.monotonic()
    cached = _EXPLAIN_CACHE.get(cache_key)
    if (
        cached
        and RECOMMENDATIONS_EXPLAIN_CACHE_TTL_SECONDS > 0
        and now_ts - cached[0] <= RECOMMENDATIONS_EXPLAIN_CACHE_TTL_SECONDS
    ):
        return cached[1]

    run_row = rec_svc.get_run_for_user(rid, user_id)
    if not run_row:
        raise HTTPException(status_code=404, detail="Run not found")
    item = rec_svc.get_item_for_run_symbol(rid, sym)
    if not item:
        raise HTTPException(status_code=404, detail="Symbol not found in run")

    risk = risk_svc.get_risk_profile(user_id) or {}
    auth_header = request.headers.get("Authorization") if request else None
    finance_ctx = None
    if risk.get("use_finance_data_for_recommendations") and auth_header:
        try:
            finance_ctx = fetch_finance_context(auth_header)
        except Exception:
            finance_ctx = None
    expl = dict(item.get("explanation_json") or {})
    sec = expl.get("security") or get_security_info(sym)
    if sec and not expl.get("security"):
        expl["security"] = sec
    elif not expl.get("security"):
        expl["security"] = {
            "full_name": sym,
            "sector": "—",
            "description": "",
            "asset_type": "unknown",
            "why_it_matters": "",
        }
    end_dt = datetime.now(timezone.utc)
    await _enrich_explanation_for_symbol(
        expl,
        sym,
        market_router,
        end_dt,
        end_dt - timedelta(days=30),
        end_dt - timedelta(days=365),
    )
    augment_explanation_for_detail(expl, risk, finance_ctx, sym)
    prev_run = rec_svc.get_previous_run_for_user(rid, user_id)
    if prev_run:
        prev_item = rec_svc.get_item_for_run_symbol(prev_run["run_id"], sym)
        if prev_item:
            try:
                cur_score = float(item.get("score") or 0.0)
                prev_score = float(prev_item.get("score") or 0.0)
                expl["score_delta_vs_prior_run"] = round(cur_score - prev_score, 6)
            except Exception:
                expl["score_delta_vs_prior_run"] = None
    if "uncertainty_bucket" not in expl:
        # Preserve backward compatibility for older runs.
        conf = float(item.get("confidence") or 0.0)
        expl["uncertainty_bucket"] = "low" if conf >= 0.75 else ("medium" if conf >= 0.5 else "high")
    response = {
        "run_id": run_id,
        "symbol": sym,
        "score": str(item.get("score")),
        "confidence": str(item.get("confidence")),
        "explanation": expl,
    }
    _EXPLAIN_CACHE[cache_key] = (now_ts, response)
    return response

