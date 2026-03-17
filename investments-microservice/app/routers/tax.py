"""
Tax-loss harvesting: harvesting opportunities and record-sale.
"""
from decimal import Decimal
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.core.config import TAX_LOSS_THRESHOLD_DOLLARS
from app.core.dependencies import get_current_user_id
from app.services.holdings_data_service import HoldingsDataService
from app.services.service_factory import ServiceFactory
from app.services.tax_harvesting_scanner import scan_harvesting_opportunities
from app.services.market_data_router import MarketDataRouter, get_default_market_data_router

router = APIRouter(prefix="/api/v1", tags=["tax"])


def _db_context() -> Dict[str, Any]:
    from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
    return {
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "dbname": DB_NAME or "investments_db",
    }


def _get_data_service() -> HoldingsDataService:
    ds = ServiceFactory.get_service("HoldingsDataService")
    if not isinstance(ds, HoldingsDataService):
        raise RuntimeError("HoldingsDataService not available")
    return ds


def _get_market_router() -> MarketDataRouter:
    return get_default_market_data_router()


@router.get("/tax/harvesting-opportunities", response_model=dict)
async def get_harvesting_opportunities(
    user_id: int = Depends(get_current_user_id),
    threshold: float = TAX_LOSS_THRESHOLD_DOLLARS,
):
    """List lots with harvestable loss above threshold; wash-sale risk and suggested replacement."""
    ds = _get_data_service()
    market_router = _get_market_router()
    rows = ds.list_all_holdings_for_user(user_id)
    symbols = list({(r.get("symbol") or "").strip().upper() for r in rows if (r.get("symbol") or "").strip()})
    symbol_to_price: Dict[str, Decimal] = {}
    for sym in symbols:
        try:
            quote, _, _ = await market_router.get_quote_with_meta(sym)
            if quote and quote.price and quote.price > 0:
                symbol_to_price[sym] = quote.price
        except Exception:
            pass
    context = _db_context()
    opportunities = scan_harvesting_opportunities(
        context, user_id, symbol_to_price, loss_threshold_dollars=threshold,
    )
    return {
        "opportunities": opportunities,
        "threshold_dollars": threshold,
    }


@router.post("/tax/record-sale", response_model=dict)
async def record_sale(
    user_id: int = Depends(get_current_user_id),
    symbol: str = "",
    quantity: float = 0,
    lot_id_ref: str | None = None,
):
    """Record a sale for wash-sale lookback (optional lot_id_ref)."""
    from datetime import date
    import psycopg2
    from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
    if not symbol or quantity <= 0:
        return {"ok": False, "detail": "symbol and quantity required"}
    conn = psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "investments_db",
    )
    conn.autocommit = False
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO investments_db.transaction (user_id, symbol, type, quantity, transaction_date, lot_id_ref)
               VALUES (%s, %s, 'sell', %s, %s, %s)""",
            (user_id, symbol.upper(), quantity, date.today(), lot_id_ref),
        )
        conn.commit()
        return {"ok": True, "symbol": symbol, "quantity": quantity}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "detail": str(e)}
    finally:
        conn.close()
