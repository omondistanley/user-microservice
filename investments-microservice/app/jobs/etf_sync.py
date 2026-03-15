"""
ETF composition sync job: fetch composition CSV for configured ETFs and upsert into etf_holding.
Run weekly or on-demand. Can be invoked via: python -m app.jobs.etf_sync
"""
import logging
import sys

from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    ETF_SYMBOLS_TO_SYNC,
)
from app.services.etf_composition_loader import (
    fetch_composition,
    get_composition_urls,
    upsert_etf_holdings,
)
from app.services.holdings_data_service import HoldingsDataService

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


def run_etf_composition_sync() -> dict:
    """
    Sync ETF compositions: for each symbol with a URL in config (or in holdings + URL),
    fetch CSV and upsert etf_holding. Returns { "synced": [symbols], "skipped": [...], "errors": [...] }.
    """
    urls = get_composition_urls()
    context = _db_context()
    holdings_svc = HoldingsDataService(context=context)
    symbols_from_holdings = set(holdings_svc.list_distinct_symbols())
    symbols_from_config = {s.strip().upper() for s in (ETF_SYMBOLS_TO_SYNC or "").split(",") if s.strip()}
    all_symbols = symbols_from_holdings | symbols_from_config
    synced = []
    skipped = []
    errors = []
    for symbol in sorted(all_symbols):
        url = urls.get(symbol) or urls.get(symbol.upper())
        if not url:
            skipped.append(symbol)
            continue
        constituents = fetch_composition(symbol, url)
        if not constituents:
            errors.append(symbol)
            continue
        try:
            n = upsert_etf_holdings(context, symbol, constituents, source="csv")
            synced.append(symbol)
            logger.info("etf_sync symbol=%s constituents=%d", symbol, n)
        except Exception as e:
            logger.exception("etf_sync_failed symbol=%s", symbol)
            errors.append(symbol)
    return {"synced": synced, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    result = run_etf_composition_sync()
    logger.info("etf_composition_sync result=%s", result)
    sys.exit(0 if not result.get("errors") else 1)
