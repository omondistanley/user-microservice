"""News aggregator: Benzinga first, then Finnhub (and optionally Alpha Vantage) as supplement."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set

from app.core.config import NEWS_PROVIDER_ORDER
from app.services.benzinga_adapter import get_news as benzinga_get_news
from app.services.finnhub_news import get_company_news as finnhub_get_company_news


def _normalize_item(raw: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """Normalize to common shape: title, url, summary, published_at, source_provider, symbols."""
    return {
        "title": raw.get("title"),
        "url": raw.get("url"),
        "summary": raw.get("summary_or_body"),
        "published_at": raw.get("published_at"),
        "source_provider": provider,
        "symbols": raw.get("symbols") or [],
    }


def _dedupe_by_title_url(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        key = (str(it.get("title") or "").strip() or "") + "|" + (str(it.get("url") or "").strip() or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def get_news_for_symbols(
    symbols: List[str],
    limit_per_symbol: int = 5,
    max_total: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch news for the given symbols. Tries Benzinga first, then supplements with Finnhub.
    Returns list of normalized items, deduped by title/url, sorted by published_at desc, trimmed to max_total.
    """
    if not symbols:
        return []
    syms = [s.strip().upper() for s in symbols if (s or "").strip()]
    if not syms:
        return []
    order = [p.strip().lower() for p in (NEWS_PROVIDER_ORDER or "").split(",") if p.strip()]
    if not order:
        order = ["benzinga", "finnhub"]
    collected: List[Dict[str, Any]] = []
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=30)

    for provider in order:
        if provider == "benzinga":
            try:
                raw_list = benzinga_get_news(syms, limit=min(limit_per_symbol * len(syms), max_total), from_date=start_dt, to_date=end_dt)
                for r in raw_list:
                    collected.append(_normalize_item(r, "benzinga"))
            except Exception:
                pass
        elif provider == "finnhub":
            for sym in syms:
                try:
                    raw_list = finnhub_get_company_news(sym, limit=limit_per_symbol, from_date=start_dt, to_date=end_dt)
                    for r in raw_list:
                        collected.append(_normalize_item(r, "finnhub"))
                except Exception:
                    pass

    collected = _dedupe_by_title_url(collected)
    try:
        collected.sort(key=lambda x: (x.get("published_at") or ""), reverse=True)
    except Exception:
        pass
    return collected[:max_total]


def get_news_for_symbol(symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Convenience: news for a single symbol."""
    return get_news_for_symbols([symbol], limit_per_symbol=limit, max_total=limit)
