"""
Resolve portfolio positions to underlying exposure (ETF look-through).
For ETFs: expand via etf_holding weights; for equities: 100% to self.
Returns aggregated exposure by underlying symbol (and optionally by sector).
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List

from app.services.sector_resolver import resolve_sector


SCHEMA = "investments_db"
ETF_HOLDING_TABLE = "etf_holding"


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


def get_etf_constituents(context: Dict[str, Any], etf_symbol: str) -> List[Dict[str, Any]]:
    """Return list of { constituent_symbol, weight_pct } for the ETF."""
    conn = _get_connection(context)
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT constituent_symbol, weight_pct FROM "{SCHEMA}"."{ETF_HOLDING_TABLE}" '
            "WHERE etf_symbol = %s ORDER BY weight_pct DESC",
            (etf_symbol.upper(),),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_look_through_exposure(
    context: Dict[str, Any],
    positions: List[Dict[str, Any]],
    include_sector: bool = False,
) -> Dict[str, Any]:
    """
    positions: list of { "symbol": str, "quantity": Decimal, "value": Decimal }.
    Returns: {
        "underlying_exposure": [ {"symbol": str, "value": float, "pct": float}, ... ],
        "total_value": float,
        "by_sector": [ {"name": str, "value": float, "pct": float}, ... ]  # if include_sector
    }
    """
    # value by underlying symbol
    underlying_value: Dict[str, Decimal] = defaultdict(Decimal)
    total_value = Decimal("0")
    for pos in positions:
        symbol = (pos.get("symbol") or "").strip().upper()
        value = pos.get("value")
        if value is None:
            continue
        if isinstance(value, (int, float)):
            value = Decimal(str(value))
        total_value += value
        constituents = get_etf_constituents(context, symbol)
        if constituents:
            for c in constituents:
                sym = (c.get("constituent_symbol") or "").strip().upper()
                w = c.get("weight_pct") or 0
                if isinstance(w, (int, float)):
                    w = Decimal(str(w)) / Decimal("100")
                else:
                    w = Decimal("0")
                underlying_value[sym] += value * w
        else:
            underlying_value[symbol] += value
    total_float = float(total_value) if total_value else 0.0
    underlying_list = [
        {
            "symbol": sym,
            "value": round(float(v), 2),
            "pct": round(float(v) / total_float * 100, 2) if total_float else 0,
        }
        for sym, v in sorted(underlying_value.items(), key=lambda x: -float(x[1]))
    ]
    result: Dict[str, Any] = {
        "underlying_exposure": underlying_list,
        "total_value": round(total_float, 2),
    }
    if include_sector:
        sector_values: Dict[str, Decimal] = defaultdict(Decimal)
        for sym, val in underlying_value.items():
            sector = resolve_sector(context, sym)
            sector_values[sector] += val
        by_sector = [
            {
                "name": name,
                "value": round(float(v), 2),
                "pct": round(float(v) / total_float * 100, 2) if total_float else 0,
            }
            for name, v in sorted(sector_values.items(), key=lambda x: -float(x[1]))
        ]
        result["by_sector"] = by_sector
    return result
