"""
Aggregate portfolio positions by sector; compute sector weights and concentration warning.
Positions are expected to have symbol, quantity, and value (market value per position).
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List

from app.core.config import SECTOR_CONCENTRATION_THRESHOLD_PCT
from app.services.sector_resolver import resolve_sector


def aggregate_by_sector(
    context: Dict[str, Any],
    positions: List[Dict[str, Any]],
    threshold_pct: float = None,
) -> Dict[str, Any]:
    """
    positions: list of { "symbol": str, "quantity": Decimal, "value": Decimal } (value = position market value).
    Returns: {
        "sectors": [ {"name": str, "pct": float, "value": float}, ... ],
        "concentration_warning": bool,
        "threshold_pct": float,
        "total_value": float,
    }
    """
    threshold_pct = threshold_pct if threshold_pct is not None else SECTOR_CONCENTRATION_THRESHOLD_PCT
    total_value = Decimal("0")
    sector_values: Dict[str, Decimal] = defaultdict(Decimal)
    for pos in positions:
        value = pos.get("value")
        if value is None:
            continue
        if isinstance(value, (int, float)):
            value = Decimal(str(value))
        total_value += value
        symbol = (pos.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        sector = resolve_sector(context, symbol)
        sector_values[sector] += value
    total_float = float(total_value) if total_value else 0.0
    sectors_list: List[Dict[str, Any]] = []
    for sector_name, val in sorted(sector_values.items(), key=lambda x: -float(x[1])):
        pct = (float(val) / total_float * 100) if total_float else 0.0
        sectors_list.append({
            "name": sector_name,
            "pct": round(pct, 2),
            "value": round(float(val), 2),
        })
    concentration_warning = any(
        s["pct"] >= threshold_pct for s in sectors_list
    )
    return {
        "sectors": sectors_list,
        "concentration_warning": concentration_warning,
        "threshold_pct": threshold_pct,
        "total_value": round(total_float, 2),
    }
