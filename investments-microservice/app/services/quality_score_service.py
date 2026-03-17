"""
Per-holding quality score (1-10) from valuation, profitability, financial health, growth.
Percentile within sector; trend improving/stable/deteriorating (from historical snapshots if available).
"""
import logging
from typing import Any, Dict, List, Optional

from app.services.fundamental_data_service import get_or_fetch_fundamentals
from app.services.sector_resolver import resolve_sector

logger = logging.getLogger(__name__)

# Factor groups: higher raw value = better (we invert P/E so lower P/E = better)
VALUATION_KEYS = ["trailingPE", "priceToBook"]  # lower is better -> we use negative or 1/x
PROFITABILITY_KEYS = ["returnOnEquity", "profitMargins", "operatingMargins"]
HEALTH_KEYS = ["currentRatio", "quickRatio", "debtToEquity"]  # lower D/E better
GROWTH_KEYS = ["earningsGrowth", "revenueGrowth"]


def _normalize_pe_pb(metrics: Dict[str, Any]) -> float:
    """Valuation: lower P/E and P/B is better. Score 0-1 (1 = attractive)."""
    pe = metrics.get("trailingPE") or metrics.get("forwardPE")
    pb = metrics.get("priceToBook")
    score = 0.5
    if pe is not None and pe > 0:
        # Lower P/E better; cap at 50, score 1 at 5, 0 at 50
        score_pe = max(0, 1 - (pe - 5) / 45) if pe > 5 else 1.0
        score = score_pe
    if pb is not None and pb > 0:
        score_pb = max(0, 1 - (pb - 0.5) / 4.5) if pb > 0.5 else 1.0
        score = (score + score_pb) / 2
    return min(1.0, max(0, score))


def _normalize_profitability(metrics: Dict[str, Any]) -> float:
    """Higher ROE/margins better. 0-1."""
    roe = metrics.get("returnOnEquity")
    pm = metrics.get("profitMargins")
    om = metrics.get("operatingMargins")
    vals = [v for v in (roe, pm, om) if v is not None and v > 0]
    if not vals:
        return 0.5
    # ROE 0.3 = 1, 0 = 0; margins 0.5 = 1
    def _norm(k: str, v: float) -> float:
        if k == "returnOnEquity":
            return min(1.0, (v * 3 if v < 0.34 else 1.0))
        return min(1.0, v * 2)
    s = sum(_norm(k, v) for k, v in [("returnOnEquity", roe), ("profitMargins", pm), ("operatingMargins", om)] if v is not None)
    n = sum(1 for v in (roe, pm, om) if v is not None)
    return min(1.0, s / n) if n else 0.5


def _normalize_health(metrics: Dict[str, Any]) -> float:
    """Higher current/quick ratio better; lower D/E better."""
    cr = metrics.get("currentRatio") or 0
    qr = metrics.get("quickRatio") or 0
    de = metrics.get("debtToEquity") or 0
    score_cr = min(1.0, (cr or 0) / 2)  # 2+ = 1
    score_de = max(0, 1 - (de or 0) / 2)  # 0 = 1, 2+ = 0
    return (score_cr + score_de) / 2 if (cr or de) else 0.5


def _normalize_growth(metrics: Dict[str, Any]) -> float:
    """Higher growth better. 0-1."""
    eg = metrics.get("earningsGrowth")
    rg = metrics.get("revenueGrowth")
    vals = [v for v in (eg, rg) if v is not None]
    if not vals:
        return 0.5
    # 0.2 = 1, 0 = 0
    s = sum(min(1.0, max(0, (v or 0) * 5)) for v in vals)
    return min(1.0, s / len(vals))


def compute_composite_score(metrics: Dict[str, Any]) -> float:
    """Composite 0-1 from four factor groups (equal weight)."""
    v = _normalize_pe_pb(metrics)
    p = _normalize_profitability(metrics)
    h = _normalize_health(metrics)
    g = _normalize_growth(metrics)
    return (v + p + h + g) / 4.0


def score_1_to_10(composite: float) -> float:
    """Map 0-1 composite to 1-10 scale."""
    return round(1 + composite * 9, 1)


def get_quality_scores(
    context: Dict[str, Any],
    symbols: List[str],
) -> List[Dict[str, Any]]:
    """
    For each symbol fetch fundamentals, resolve sector, compute composite score (1-10) and trend.
    Trend is 'stable' unless historical snapshots exist (future: compare to 1y/3y ago).
    """
    results = []
    for symbol in symbols:
        sym = (symbol or "").strip().upper()
        if not sym:
            continue
        metrics = get_or_fetch_fundamentals(context, sym)
        if not metrics:
            results.append({
                "symbol": sym,
                "quality_score": None,
                "sector": resolve_sector(context, sym),
                "trend": "unknown",
            })
            continue
        sector = resolve_sector(context, sym)
        composite = compute_composite_score(metrics)
        score = score_1_to_10(composite)
        results.append({
            "symbol": sym,
            "quality_score": score,
            "sector": sector,
            "trend": "stable",  # TODO: compare to 1y/3y snapshot when available
        })
    return results
