"""Finnhub company news. Supplement to Benzinga news pipeline."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import FINNHUB_API_KEY, FINNHUB_BASE_URL, NEWS_TIMEOUT_SECONDS


def _parse_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(int(value), tz=timezone.utc)
            return dt.isoformat()
        except Exception:
            return None
    return str(value).strip() or None


def get_company_news(
    symbol: str,
    limit: int = 10,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch company news from Finnhub for one symbol.
    Returns list of items: id, title, url, summary_or_body, published_at, source, symbols.
    """
    if not FINNHUB_API_KEY or not FINNHUB_BASE_URL:
        return []
    sym = (symbol or "").strip().upper()
    if not sym:
        return []
    end = to_date or datetime.now(timezone.utc)
    start = from_date or (end - timedelta(days=30))
    params: Dict[str, Any] = {
        "symbol": sym,
        "from": start.strftime("%Y-%m-%d"),
        "to": end.strftime("%Y-%m-%d"),
        "token": FINNHUB_API_KEY,
    }
    url = f"{FINNHUB_BASE_URL.rstrip('/')}/company-news"
    try:
        with httpx.Client(timeout=NEWS_TIMEOUT_SECONDS) as client:
            resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in data[:limit]:
        if not isinstance(item, dict):
            continue
        out.append({
            "id": item.get("id"),
            "title": (item.get("headline") or "").strip() or None,
            "url": (item.get("url") or "").strip() or None,
            "summary_or_body": (item.get("summary") or "").strip() or None,
            "published_at": _parse_datetime(item.get("datetime")),
            "source": "finnhub",
            "symbols": [sym],
        })
    return out
