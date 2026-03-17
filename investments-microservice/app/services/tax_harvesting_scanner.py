"""
Tax-loss harvesting scanner: identify lots with unrealized loss above threshold; wash-sale check.
Uses tax_lot when present; otherwise treats holding as one synthetic lot (avg_cost, quantity, created_at).
"""
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA = "investments_db"
LOSS_THRESHOLD_DEFAULT = 200  # minimum $ loss to suggest harvesting


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


def get_lots_for_holding(
    context: Dict[str, Any],
    holding_id: str,
    symbol: str,
    quantity: Decimal,
    avg_cost: Decimal,
    created_at: Any,
) -> List[Dict[str, Any]]:
    """
    Return list of lots for this holding. If no rows in tax_lot, return one synthetic lot.
    Each lot: { lot_id, holding_id, symbol, quantity, cost_per_share, purchase_date, cost_basis }.
    """
    conn = _get_connection(context)
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT lot_id, holding_id, quantity, cost_per_share, purchase_date FROM "{SCHEMA}".tax_lot '
            "WHERE holding_id = %s ORDER BY purchase_date ASC",
            (holding_id,),
        )
        rows = cur.fetchall()
        if rows:
            return [
                {
                    "lot_id": str(r["lot_id"]),
                    "holding_id": str(r["holding_id"]),
                    "symbol": symbol,
                    "quantity": Decimal(str(r["quantity"])),
                    "cost_per_share": Decimal(str(r["cost_per_share"])),
                    "purchase_date": r["purchase_date"],
                    "cost_basis": Decimal(str(r["quantity"])) * Decimal(str(r["cost_per_share"])),
                }
                for r in rows
            ]
        # Synthetic lot from holding
        purchase_d = created_at.date() if hasattr(created_at, "date") else date.today()
        return [
            {
                "lot_id": None,
                "holding_id": str(holding_id),
                "symbol": symbol,
                "quantity": quantity,
                "cost_per_share": avg_cost,
                "purchase_date": purchase_d,
                "cost_basis": quantity * avg_cost,
            }
        ]
    finally:
        conn.close()


def get_buys_in_window(
    context: Dict[str, Any],
    user_id: int,
    symbol: str,
    window_start: date,
    window_end: date,
) -> bool:
    """True if there is a buy of this symbol by user in [window_start, window_end] (wash-sale risk)."""
    conn = _get_connection(context)
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT 1 FROM "{SCHEMA}".transaction '
            "WHERE user_id = %s AND symbol = %s AND type = 'buy' AND transaction_date BETWEEN %s AND %s LIMIT 1",
            (user_id, symbol.upper(), window_start, window_end),
        )
        return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        conn.close()


def scan_harvesting_opportunities(
    context: Dict[str, Any],
    user_id: int,
    symbol_to_price: Dict[str, Decimal],
    loss_threshold_dollars: float = LOSS_THRESHOLD_DEFAULT,
    wash_sale_days: int = 30,
) -> List[Dict[str, Any]]:
    """
    For each holding of user, resolve lots (or synthetic); compute unrealized loss; check wash-sale.
    symbol_to_price: map symbol -> current price (from quotes).
    Returns list of { lot_id, holding_id, symbol, quantity, cost_basis, current_value, unrealized_loss,
                     harvestable_loss, wash_sale_risk, suggested_replacement }.
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(
        host=context.get("host", "localhost"),
        port=int(context.get("port", 5432)),
        user=context.get("user", "postgres"),
        password=context.get("password", "postgres"),
        dbname=context.get("dbname", "investments_db"),
        cursor_factory=RealDictCursor,
    )
    today = date.today()
    window_start = today - timedelta(days=wash_sale_days)
    window_end = today + timedelta(days=wash_sale_days)
    opportunities = []
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT holding_id, symbol, quantity, avg_cost, created_at FROM "{SCHEMA}".holding WHERE user_id = %s',
            (user_id,),
        )
        holdings = cur.fetchall()
        for h in holdings:
            holding_id = str(h["holding_id"])
            symbol = (h["symbol"] or "").strip().upper()
            quantity = Decimal(str(h["quantity"] or 0))
            avg_cost = Decimal(str(h["avg_cost"] or 0))
            created_at = h.get("created_at") or today
            price = symbol_to_price.get(symbol)
            if price is None or price <= 0:
                continue
            lots = get_lots_for_holding(context, holding_id, symbol, quantity, avg_cost, created_at)
            for lot in lots:
                cost_basis = lot["cost_basis"]
                qty = lot["quantity"]
                cost_per_share = lot["cost_per_share"]
                current_value = qty * price
                unrealized_loss = cost_basis - current_value
                if unrealized_loss < 0 and abs(float(unrealized_loss)) >= loss_threshold_dollars:
                    wash_sale_risk = get_buys_in_window(context, user_id, symbol, window_start, window_end)
                    opportunities.append({
                        "lot_id": lot.get("lot_id"),
                        "holding_id": holding_id,
                        "symbol": symbol,
                        "quantity": float(qty),
                        "cost_basis": float(cost_basis),
                        "current_value": float(current_value),
                        "unrealized_loss": float(unrealized_loss),
                        "harvestable_loss": abs(float(unrealized_loss)),
                        "wash_sale_risk": wash_sale_risk,
                        "suggested_replacement": _suggest_replacement(symbol),
                    })
    finally:
        conn.close()
    return opportunities


def _suggest_replacement(symbol: str) -> Optional[str]:
    """Heuristic: suggest similar but not substantially identical ticker (e.g. VTI vs ITOT)."""
    # Simple map for common pairs; extend as needed
    replacements = {
        "VTI": "ITOT",
        "ITOT": "VTI",
        "VOO": "IVV",
        "IVV": "VOO",
        "SPY": "IVV",
    }
    return replacements.get(symbol.upper())
