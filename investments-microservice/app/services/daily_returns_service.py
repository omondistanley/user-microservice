"""
Daily returns for correlation: from price_bar (interval=1d) or yfinance backfill.
Ensures at least 90 days of daily returns per symbol where possible.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA = "investments_db"
TABLE = "price_bar"
ROLLING_DAYS = 90


def _get_connection(context: Dict[str, Any]):
    import psycopg2
    from psycopg2.extras import RealDictCursor
    return psycopg2.connect(
        host=context.get("host", "localhost"),
        port=int(context.get("port", 5432)),
        user=context.get("user", "postgres"),
        password=context.get("password", "postgres"),
        dbname=context.get("dbname", "investments_db"),
        cursor_factory=RealDictCursor,
    )


def get_daily_returns_from_bars(
    context: Dict[str, Any],
    symbol: str,
    days: int = ROLLING_DAYS,
) -> List[float]:
    """
    Get list of daily return percentages (oldest to newest) from price_bar.
    Return empty list if insufficient data. Uses interval='1d' and period_start/close from 001 schema.
    """
    conn = _get_connection(context)
    try:
        cur = conn.cursor()
        # Support 001 schema (period_start, interval) or 002 (ts, bar_interval)
        try:
            cur.execute(
                f'''SELECT period_start, close FROM "{SCHEMA}"."{TABLE}"
                 WHERE symbol = %s AND interval = '1d' ORDER BY period_start ASC''',
                (symbol.upper(),),
            )
        except Exception:
            cur.execute(
                f'''SELECT ts AS period_start, close FROM "{SCHEMA}"."{TABLE}"
                 WHERE symbol = %s AND bar_interval = '1d' ORDER BY ts ASC''',
                (symbol.upper(),),
            )
        rows = cur.fetchall()
        if not rows or len(rows) < 2:
            return []
        # Build returns: (close_t - close_t-1) / close_t-1 * 100
        out = []
        for i in range(1, len(rows)):
            prev_close = float(rows[i - 1].get("close", 0) or 0)
            curr_close = float(rows[i].get("close", 0) or 0)
            if prev_close and prev_close > 0:
                out.append((curr_close - prev_close) / prev_close * 100)
        # Last `days` returns
        return out[-days:] if len(out) > days else out
    except Exception as e:
        logger.debug("daily_returns_from_bars symbol=%s error=%s", symbol, e)
        return []
    finally:
        conn.close()


def backfill_daily_bars_yfinance(context: Dict[str, Any], symbol: str, days: int = 120) -> int:
    """
    Fetch daily OHLCV from yfinance and insert into price_bar (001 schema).
    Returns number of bars inserted. Idempotent (uses unique constraint if any; else may duplicate).
    """
    try:
        import yfinance as yf
    except ImportError:
        return 0
    try:
        ticker = yf.Ticker(symbol.upper())
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        hist = ticker.history(start=start, end=end, interval="1d")
        if hist is None or hist.empty:
            return 0
        import psycopg2
        conn = psycopg2.connect(
            host=context.get("host", "localhost"),
            port=int(context.get("port", 5432)),
            user=context.get("user", "postgres"),
            password=context.get("password", "postgres"),
            dbname=context.get("dbname", "investments_db"),
        )
        conn.autocommit = False
        inserted = 0
        try:
            cur = conn.cursor()
            for ts, row in hist.iterrows():
                if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                period_start = ts
                o, h, l, c, v = row.get("Open"), row.get("High"), row.get("Low"), row.get("Close"), row.get("Volume")
                if c is None or (hasattr(c, "item") and str(c) == "nan"):
                    continue
                cur.execute(
                    f'''INSERT INTO "{SCHEMA}"."{TABLE}" (symbol, interval, period_start, open, high, low, close, volume)
                     VALUES (%s, '1d', %s, %s, %s, %s, %s, %s)''',
                    (symbol.upper(), period_start, float(o or c), float(h or c), float(l or c), float(c), float(v or 0)),
                )
                inserted += 1
            conn.commit()
        finally:
            conn.close()
        return inserted
    except Exception as e:
        logger.warning("backfill_daily_bars symbol=%s error=%s", symbol, e)
        return 0


def get_returns_matrix(
    context: Dict[str, Any],
    symbols: List[str],
    days: int = ROLLING_DAYS,
    backfill_if_missing: bool = True,
) -> Dict[str, List[float]]:
    """
    Return map symbol -> list of daily return % (aligned by index; shorter series padded with None or truncated).
    For correlation we need aligned dates; simplest is to truncate all to min length.
    """
    matrix = {}
    for sym in symbols:
        returns = get_daily_returns_from_bars(context, sym, days=days)
        if not returns and backfill_if_missing:
            backfill_daily_bars_yfinance(context, sym, days=days + 30)
            returns = get_daily_returns_from_bars(context, sym, days=days)
        matrix[sym] = returns
    return matrix
