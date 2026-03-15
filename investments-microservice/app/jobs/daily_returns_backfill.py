"""
Nightly backfill of daily price bars for held symbols (for correlation matrix).
Run: python -m app.jobs.daily_returns_backfill
"""
import logging
import sys

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.services.daily_returns_service import backfill_daily_bars_yfinance
from app.services.holdings_data_service import HoldingsDataService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROLLING_DAYS = 120


def _db_context():
    return {
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "dbname": DB_NAME or "investments_db",
    }


def run_daily_returns_backfill() -> dict:
    """Backfill daily bars for all distinct symbols in holdings. Returns { symbol: bars_inserted }."""
    context = _db_context()
    svc = HoldingsDataService(context=context)
    symbols = svc.list_distinct_symbols()
    result = {}
    for sym in symbols:
        n = backfill_daily_bars_yfinance(context, sym, days=ROLLING_DAYS)
        result[sym] = n
        if n:
            logger.info("daily_returns_backfill symbol=%s inserted=%d", sym, n)
    return result


if __name__ == "__main__":
    run_daily_returns_backfill()
    sys.exit(0)
