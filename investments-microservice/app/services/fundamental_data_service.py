"""
Fetch and cache fundamental metrics (P/E, P/B, ROE, margins, D/E, growth) from yfinance.
"""
import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA = "investments_db"
TABLE = "fundamental_snapshot"

METRIC_KEYS = (
    "trailingPE", "forwardPE", "priceToBook", "returnOnEquity", "returnOnAssets",
    "profitMargins", "operatingMargins", "debtToEquity", "earningsGrowth", "revenueGrowth",
    "currentRatio", "quickRatio",
)


def _get_connection(context: Dict[str, Any]):
    import psycopg2
    return psycopg2.connect(
        host=context.get("host", "localhost"),
        port=int(context.get("port", 5432)),
        user=context.get("user", "postgres"),
        password=context.get("password", "postgres"),
        dbname=context.get("dbname", "investments_db"),
    )


def fetch_fundamentals_yfinance(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch fundamental metrics from yfinance. Returns dict of metric key -> value or None."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol.upper())
        info = t.info
        if not info:
            return None
        out = {}
        for k in METRIC_KEYS:
            v = info.get(k)
            if v is not None and str(v) != "nan":
                try:
                    out[k] = float(v)
                except (TypeError, ValueError):
                    pass
        return out if out else None
    except Exception as e:
        logger.debug("yfinance_fundamentals symbol=%s error=%s", symbol, e)
        return None


def get_cached_snapshot(context: Dict[str, Any], symbol: str, period_end: date) -> Optional[Dict[str, Any]]:
    """Return cached metrics_json for symbol/period_end or None."""
    conn = _get_connection(context)
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT metrics_json FROM "{SCHEMA}"."{TABLE}" WHERE symbol = %s AND period_end = %s',
            (symbol.upper(), period_end),
        )
        row = cur.fetchone()
        if row:
            m = row[0]
            return m if isinstance(m, dict) else json.loads(m or "{}")
        return None
    finally:
        conn.close()


def upsert_snapshot(
    context: Dict[str, Any],
    symbol: str,
    period_end: date,
    metrics: Dict[str, Any],
) -> None:
    """Insert or update fundamental_snapshot row."""
    conn = _get_connection(context)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        cur.execute(
            f'''INSERT INTO "{SCHEMA}"."{TABLE}" (symbol, period_end, metrics_json, updated_at)
               VALUES (%s, %s, %s, now())
               ON CONFLICT (symbol, period_end) DO UPDATE SET metrics_json = EXCLUDED.metrics_json, updated_at = now()''',
            (symbol.upper(), period_end, json.dumps(metrics)),
        )
        conn.commit()
    finally:
        conn.close()


def get_or_fetch_fundamentals(
    context: Dict[str, Any],
    symbol: str,
    period_end: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """Return cached metrics or fetch from yfinance and cache. period_end defaults to today."""
    period_end = period_end or date.today()
    cached = get_cached_snapshot(context, symbol, period_end)
    if cached:
        return cached
    metrics = fetch_fundamentals_yfinance(symbol)
    if metrics:
        upsert_snapshot(context, symbol, period_end, metrics)
        return metrics
    return None
