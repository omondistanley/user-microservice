"""Benzinga News API adapter. Fetches news by tickers; normalizes to common NewsItem shape."""
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import (
    BENZINGA_API_KEY,
    BENZINGA_BASE_URL,
    NEWS_PAGE_SIZE,
    NEWS_TIMEOUT_SECONDS,
)


def _parse_benzinga_date(value: Any) -> Optional[str]:
    """Return string for published_at or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    s = str(value).strip()
    return s if s else None


def get_news(
    symbols: List[str],
    limit: int = 10,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch news from Benzinga for the given symbols.
    Returns list of normalized items: id, title, url, summary_or_body, published_at, source, symbols.
    """
    if not BENZINGA_API_KEY or not BENZINGA_BASE_URL:
        return []
    tickers = ",".join((s or "").strip().upper() for s in symbols if (s or "").strip())[:200]
    if not tickers:
        return []
    params: Dict[str, Any] = {
        "pageSize": min(limit, NEWS_PAGE_SIZE, 100),
        "page": 0,
        "tickers": tickers,
    }
    if from_date:
        params["dateFrom"] = from_date.strftime("%Y-%m-%d")
    if to_date:
        params["dateTo"] = to_date.strftime("%Y-%m-%d")
    url = f"{BENZINGA_BASE_URL.rstrip('/')}/api/v2/news"
    headers = {
        "Authorization": f"token {BENZINGA_API_KEY}",
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=NEWS_TIMEOUT_SECONDS) as client:
            resp = client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_created = item.get("created") or item.get("updated")
        published_at = _parse_benzinga_date(raw_created)
        stocks = item.get("stocks") or []
        syms = [str(s.get("name", "")).strip() for s in stocks if isinstance(s, dict) and s.get("name")]
        out.append({
            "id": item.get("id"),
            "title": (item.get("title") or "").strip() or None,
            "url": (item.get("url") or "").strip() or None,
            "summary_or_body": (item.get("teaser") or item.get("body") or "").strip() or None,
            "published_at": published_at,
            "source": "benzinga",
            "symbols": syms,
        })
    return out
