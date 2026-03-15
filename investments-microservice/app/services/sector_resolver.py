"""
Resolve sector for a symbol: read from sector_cache (with TTL), else fetch via yfinance and cache.
Falls back to security_universe.sector if present. Returns normalized sector name or "Other".
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import SECTOR_CACHE_TTL_HOURS

logger = logging.getLogger(__name__)

SCHEMA = "investments_db"
SECTOR_CACHE_TABLE = "sector_cache"
SECURITY_UNIVERSE_TABLE = "security_universe"


def _get_connection(context: Dict[str, Any]):
    return psycopg2.connect(
        host=context.get("host", "localhost"),
        port=int(context.get("port", 5432)),
        user=context.get("user", "postgres"),
        password=context.get("password", "postgres"),
        dbname=context.get("dbname", "investments_db"),
        cursor_factory=RealDictCursor,
    )


def _fetch_sector_yfinance(symbol: str) -> Optional[str]:
    """Fetch sector from yfinance. Returns None on failure."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol.upper())
        info = ticker.info
        if not info:
            return None
        sector = (info.get("sector") or info.get("industry") or "").strip()
        if sector:
            return sector[:64]
        return "Other"
    except Exception as e:
        logger.debug("yfinance_sector_failed symbol=%s error=%s", symbol, e)
        return None


def get_sector_from_cache(context: Dict[str, Any], symbol: str) -> Optional[Tuple[str, bool]]:
    """
    Return (sector, is_stale). If not in cache or stale (updated_at older than TTL), is_stale=True.
    """
    conn = _get_connection(context)
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT sector, updated_at FROM "{SCHEMA}"."{SECTOR_CACHE_TABLE}" WHERE symbol = %s',
            (symbol.upper(),),
        )
        row = cur.fetchone()
        if not row:
            return None
        sector = row.get("sector")
        updated_at = row.get("updated_at")
        if not sector:
            return None
        if updated_at:
            if isinstance(updated_at, datetime) and updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - updated_at).total_seconds()
            stale = age > (SECTOR_CACHE_TTL_HOURS * 3600)
        else:
            stale = True
        return (sector, stale)
    finally:
        conn.close()


def get_sector_from_security_universe(context: Dict[str, Any], symbol: str) -> Optional[str]:
    """Fallback: sector from security_universe if present."""
    conn = _get_connection(context)
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT sector FROM "{SCHEMA}"."{SECURITY_UNIVERSE_TABLE}" WHERE symbol = %s',
            (symbol.upper(),),
        )
        row = cur.fetchone()
        if row and row.get("sector"):
            return (row.get("sector") or "").strip()[:64] or None
        return None
    finally:
        conn.close()


def set_sector_cache(context: Dict[str, Any], symbol: str, sector: str) -> None:
    """Upsert sector into sector_cache."""
    conn = _get_connection(context)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{SECTOR_CACHE_TABLE}" (symbol, sector, updated_at) '
            "VALUES (%s, %s, now()) "
            f'ON CONFLICT (symbol) DO UPDATE SET sector = EXCLUDED.sector, updated_at = now()',
            (symbol.upper(), (sector or "Other")[:64]),
        )
        conn.commit()
    finally:
        conn.close()


def resolve_sector(context: Dict[str, Any], symbol: str) -> str:
    """
    Resolve sector for symbol: cache (if fresh), else security_universe, else yfinance then cache.
    Always returns a string (default "Other").
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return "Other"
    cached = get_sector_from_cache(context, sym)
    if cached:
        sector, stale = cached
        if not stale:
            return sector
        # Stale: try refresh from yfinance
    fallback = get_sector_from_security_universe(context, sym)
    sector = _fetch_sector_yfinance(sym)
    if sector:
        set_sector_cache(context, sym, sector)
        return sector
    if fallback:
        set_sector_cache(context, sym, fallback)
        return fallback
    if cached:
        return cached[0]
    set_sector_cache(context, sym, "Other")
    return "Other"
