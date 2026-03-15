"""
Nightly tax-loss harvesting scan: find opportunities per user, optionally publish to Redis.
Run: python -m app.jobs.tax_harvesting_job
"""
import json
import logging
import sys
from decimal import Decimal

from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    REDIS_URL,
    TAX_LOSS_THRESHOLD_DOLLARS,
)
from app.services.holdings_data_service import HoldingsDataService
from app.services.tax_harvesting_scanner import scan_harvesting_opportunities

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _db_context():
    return {
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "dbname": DB_NAME or "investments_db",
    }


def _get_prices_yfinance(symbols: list) -> dict:
    """Sync fetch current price per symbol via yfinance."""
    symbol_to_price = {}
    try:
        import yfinance as yf
        for sym in symbols:
            try:
                t = yf.Ticker(sym)
                info = t.info
                p = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
                if p is not None and float(p) > 0:
                    symbol_to_price[sym] = Decimal(str(p))
            except Exception as e:
                logger.debug("yfinance price failed symbol=%s error=%s", sym, e)
    except ImportError:
        pass
    return symbol_to_price


def run_tax_harvesting_scan() -> dict:
    """Scan all users with holdings; return and optionally publish opportunities."""
    context = _db_context()
    svc = HoldingsDataService(context=context)
    # Distinct user_ids from holdings (no user table in this service; use holding.user_id)
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(
        host=context["host"], port=context["port"], user=context["user"],
        password=context["password"], dbname=context["dbname"],
        cursor_factory=RealDictCursor,
    )
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT user_id FROM investments_db.holding")
        user_ids = [r["user_id"] for r in cur.fetchall()]
    finally:
        conn.close()
    all_opportunities = []
    for user_id in user_ids:
        rows = svc.list_all_holdings_for_user(user_id)
        symbols = list({(r.get("symbol") or "").strip().upper() for r in rows if (r.get("symbol") or "").strip()})
        symbol_to_price = _get_prices_yfinance(symbols)
        opportunities = scan_harvesting_opportunities(
            context, user_id, symbol_to_price, loss_threshold_dollars=TAX_LOSS_THRESHOLD_DOLLARS,
        )
        for opp in opportunities:
            opp["user_id"] = user_id
            all_opportunities.append(opp)
            if REDIS_URL:
                try:
                    import redis
                    r = redis.Redis.from_url(REDIS_URL)
                    r.publish("events:tax", json.dumps({
                        "event": "tax.harvesting_opportunity",
                        "user_id": user_id,
                        "payload": opp,
                    }))
                except Exception as e:
                    logger.warning("redis_publish_failed %s", e)
    return {"users_scanned": len(user_ids), "opportunities": all_opportunities}


if __name__ == "__main__":
    result = run_tax_harvesting_scan()
    logger.info("tax_harvesting_scan result count=%d", len(result.get("opportunities", [])))
    sys.exit(0)
