"""
Multi-broker CSV import parser.
Normalises broker export formats to pocketii's internal holdings schema.
Supports: Fidelity, Schwab, Vanguard, eToro, TD Ameritrade.
"""
import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BrokerParseError(Exception):
    pass


def _safe_decimal(val: str) -> Optional[Decimal]:
    if not val or val.strip() in ("", "--", "N/A", "n/a", "-"):
        return None
    cleaned = val.strip().replace("$", "").replace(",", "").replace("%", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_fidelity(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Fidelity: Symbol, Quantity, Current Value, Cost Basis Total, Average Cost Basis"""
    results = []
    for row in rows:
        symbol = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
        if not symbol or symbol in ("SPAXX", "FCASH", "--"):
            continue
        qty = _safe_decimal(row.get("Quantity") or row.get("quantity") or "")
        avg_cost = _safe_decimal(row.get("Average Cost Basis") or row.get("Average Cost Basis Per Share") or "")
        if not symbol or qty is None or qty <= 0:
            continue
        if avg_cost is None:
            cost_total = _safe_decimal(row.get("Cost Basis Total") or "")
            avg_cost = (cost_total / qty) if cost_total and qty > 0 else Decimal("0")
        results.append({"symbol": symbol, "quantity": qty, "avg_cost": avg_cost or Decimal("0"), "currency": "USD"})
    return results


def _parse_schwab(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Schwab: Symbol, Quantity, Price, Market Value, Cost Basis"""
    results = []
    for row in rows:
        symbol = (row.get("Symbol") or "").strip().upper()
        if not symbol or symbol in ("--", "SWVXX"):
            continue
        qty = _safe_decimal(row.get("Quantity") or "")
        cost_basis = _safe_decimal(row.get("Cost Basis") or "")
        if qty is None or qty <= 0:
            continue
        avg_cost = (cost_basis / qty) if cost_basis and qty > 0 else Decimal("0")
        results.append({"symbol": symbol, "quantity": qty, "avg_cost": avg_cost, "currency": "USD"})
    return results


def _parse_vanguard(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Vanguard: Symbol, Shares, Current Value, Cost Basis"""
    results = []
    for row in rows:
        symbol = (row.get("Symbol") or row.get("Ticker Symbol") or "").strip().upper()
        if not symbol:
            continue
        qty = _safe_decimal(row.get("Shares") or "")
        cost_basis = _safe_decimal(row.get("Cost Basis") or "")
        if qty is None or qty <= 0:
            continue
        avg_cost = (cost_basis / qty) if cost_basis and qty > 0 else Decimal("0")
        results.append({"symbol": symbol, "quantity": qty, "avg_cost": avg_cost, "currency": "USD"})
    return results


def _parse_etoro(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """eToro: Ticker, Units, Open Rate, Current Rate, Net Profit"""
    results = []
    for row in rows:
        symbol = (row.get("Ticker") or row.get("Symbol") or "").strip().upper()
        if not symbol:
            continue
        qty = _safe_decimal(row.get("Units") or row.get("Quantity") or "")
        avg_cost = _safe_decimal(row.get("Open Rate") or row.get("Average Price") or "")
        if qty is None or qty <= 0:
            continue
        results.append({"symbol": symbol, "quantity": qty, "avg_cost": avg_cost or Decimal("0"), "currency": "USD"})
    return results


def _parse_td(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """TD Ameritrade: Symbol, Qty, Trade Price, Mark, P&L Open"""
    results = []
    for row in rows:
        symbol = (row.get("Symbol") or "").strip().upper()
        if not symbol:
            continue
        qty = _safe_decimal(row.get("Qty") or row.get("Quantity") or "")
        avg_cost = _safe_decimal(row.get("Trade Price") or row.get("Avg Price") or "")
        if qty is None or qty <= 0:
            continue
        results.append({"symbol": symbol, "quantity": qty, "avg_cost": avg_cost or Decimal("0"), "currency": "USD"})
    return results


_PARSERS = {
    "fidelity": _parse_fidelity,
    "schwab": _parse_schwab,
    "vanguard": _parse_vanguard,
    "etoro": _parse_etoro,
    "td": _parse_td,
}

_BROKER_SIGNATURES = {
    "fidelity": {"Average Cost Basis", "Cost Basis Total"},
    "schwab": {"Cost Basis", "Market Value"},
    "vanguard": {"Shares", "Cost Basis"},
    "etoro": {"Units", "Open Rate"},
    "td": {"Trade Price", "Mark"},
}


def detect_broker(headers: List[str]) -> Optional[str]:
    """Auto-detect broker from CSV header columns."""
    header_set = {h.strip() for h in headers}
    for broker, sig in _BROKER_SIGNATURES.items():
        if sig.issubset(header_set):
            return broker
    return None


def parse_broker_csv(
    content: str,
    broker: Optional[str] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Parse broker CSV content.
    Returns (detected_broker, list of normalised holding dicts).
    Raises BrokerParseError on unrecognised format.
    """
    reader = csv.DictReader(io.StringIO(content.strip()))
    rows = list(reader)
    if not rows:
        raise BrokerParseError("CSV file is empty or has no data rows.")

    headers = list(rows[0].keys()) if rows else []
    if not broker:
        broker = detect_broker(headers)
    if not broker:
        raise BrokerParseError(
            f"Could not detect broker from headers: {headers}. "
            "Specify broker explicitly (fidelity, schwab, vanguard, etoro, td)."
        )

    parser = _PARSERS.get(broker.lower())
    if not parser:
        raise BrokerParseError(f"No parser for broker: {broker}")

    holdings = parser(rows)
    logger.info("broker_csv_parser: broker=%s rows=%d parsed=%d", broker, len(rows), len(holdings))
    return broker, holdings
