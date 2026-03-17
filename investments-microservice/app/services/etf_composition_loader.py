"""
Load ETF composition (constituent symbols and weights) from CSV URLs.
Parses common formats: iShares (Ticker, Weight), generic (ticker/symbol column, weight column).
"""
import csv
import io
import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple


import httpx

from app.core.config import ETF_COMPOSITION_URLS

logger = logging.getLogger(__name__)

# Column name variants for ticker and weight
TICKER_ALIASES = ("ticker", "symbol", "holding ticker", "holding ticker symbol", "security", "holding")
WEIGHT_ALIASES = ("weight", "weight (%)", "weight %", "market value weight", "allocation", "portfolio weight")


def _normalize_header(h: str) -> str:
    return (h or "").strip().lower()


def _find_column(row_dict: Dict[str, str], aliases: Tuple[str, ...]) -> Optional[str]:
    keys_lower = {_normalize_header(k): k for k in row_dict.keys()}
    for a in aliases:
        if a in keys_lower:
            return keys_lower[a]
    return None


def parse_composition_csv(
    raw_text: str,
    ticker_col: Optional[str] = None,
    weight_col: Optional[str] = None,
) -> List[Tuple[str, float]]:
    """
    Parse CSV content; return list of (constituent_symbol, weight_pct).
    If ticker_col/weight_col not given, auto-detect from header.
    """
    reader = csv.DictReader(io.StringIO(raw_text))
    rows = list(reader)
    if not rows:
        return []
    first = rows[0]
    ticker_key = ticker_col or _find_column(first, TICKER_ALIASES)
    weight_key = weight_col or _find_column(first, WEIGHT_ALIASES)
    if not ticker_key or not weight_key:
        return []
    out: List[Tuple[str, float]] = []
    for r in rows:
        sym = (r.get(ticker_key) or "").strip().upper()
        w = (r.get(weight_key) or "0").replace("%", "").strip()
        if not sym or sym in ("-", "N/A", "TICKER", "SYMBOL"):
            continue
        try:
            pct = float(w)
        except ValueError:
            continue
        if pct <= 0:
            continue
        out.append((sym, pct))
    return out


def get_composition_urls() -> Dict[str, str]:
    """Return symbol -> URL map from config."""
    raw = (ETF_COMPOSITION_URLS or "{}").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def fetch_composition(etf_symbol: str, url: str) -> List[Tuple[str, float]]:
    """
    Fetch CSV from url and parse into (constituent_symbol, weight_pct) list.
    Uses sync httpx so it can be called from a job or sync context.
    """
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return parse_composition_csv(resp.text)
    except Exception as e:
        logger.warning("etf_composition_fetch_failed etf=%s url=%s error=%s", etf_symbol, url, e)
        return []


def upsert_etf_holdings(
    context: Dict[str, Any],
    etf_symbol: str,
    constituents: List[Tuple[str, float]],
    source: str = "csv",
) -> int:
    """
    Upsert rows into etf_holding. Returns number of rows upserted.
    """
    import psycopg2
    from psycopg2.extras import execute_values

    if not constituents:
        return 0
    etf = etf_symbol.upper()
    as_of = date.today()
    conn = psycopg2.connect(
        host=context.get("host", "localhost"),
        port=int(context.get("port", 5432)),
        user=context.get("user", "postgres"),
        password=context.get("password", "postgres"),
        dbname=context.get("dbname", "investments_db"),
    )
    conn.autocommit = False
    try:
        cur = conn.cursor()
        # Delete existing for this ETF then insert (simplest upsert semantics)
        cur.execute(
            'DELETE FROM investments_db.etf_holding WHERE etf_symbol = %s',
            (etf,),
        )
        data = [(etf, sym, pct, as_of, source) for sym, pct in constituents]
        execute_values(
            cur,
            """INSERT INTO investments_db.etf_holding (etf_symbol, constituent_symbol, weight_pct, as_of_date, source)
               VALUES %s""",
            data,
            template="(%s, %s, %s, %s, %s)",
        )
        conn.commit()
        return len(data)
    finally:
        conn.close()
