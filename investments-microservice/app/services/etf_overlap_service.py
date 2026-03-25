"""
ETF overlap detection service.
Identifies double-exposure (direct stock + ETF) and ETF-to-ETF overlap.
Not financial advice. This is informational only.
"""
import logging
from decimal import Decimal
from typing import Any, Dict, List

import psycopg2

logger = logging.getLogger(__name__)


def _get_conn(db_context: Dict[str, Any]):
    return psycopg2.connect(
        host=db_context.get("host", "localhost"),
        port=int(db_context.get("port", 5432)),
        user=db_context.get("user", "postgres"),
        password=db_context.get("password", "postgres"),
        dbname=db_context.get("dbname", "investments_db"),
        connect_timeout=5,
    )


def _get_etf_constituents(conn, etf_symbol: str) -> Dict[str, float]:
    """Return {constituent_symbol: weight_pct} for an ETF."""
    try:
        with conn.cursor() as cur:
            # Try etf_constituent table first (migration 021), fallback to etf_holding
            try:
                cur.execute(
                    "SELECT holding_symbol, weight_pct FROM etf_constituent "
                    "WHERE etf_symbol = %s ORDER BY fetched_date DESC, weight_pct DESC",
                    (etf_symbol.upper(),),
                )
            except Exception:
                cur.execute(
                    "SELECT constituent_symbol, weight_pct FROM etf_holding "
                    "WHERE etf_symbol = %s ORDER BY weight_pct DESC",
                    (etf_symbol.upper(),),
                )
            rows = cur.fetchall()
            return {r[0]: float(r[1]) / 100.0 for r in rows if r[1]}
    except Exception as e:
        logger.debug("get_etf_constituents %s: %s", etf_symbol, e)
        return {}


def calculate_etf_overlap(
    db_context: Dict[str, Any],
    positions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    positions: list of {symbol, value, quantity} dicts
    Returns list of warning dicts for double-exposure and ETF-ETF overlap.
    """
    warnings = []
    total_value = sum(float(p.get("value", 0)) for p in positions)
    if total_value == 0:
        return []

    try:
        conn = _get_conn(db_context)
        try:
            # Simple ETF detection: check etf_constituent/etf_holding for symbols
            etf_positions = []
            stock_positions = []
            for p in positions:
                sym = (p.get("symbol") or "").upper()
                constituents = _get_etf_constituents(conn, sym)
                if constituents:
                    etf_positions.append({"symbol": sym, "weight": float(p["value"]) / total_value, "constituents": constituents})
                else:
                    stock_positions.append({"symbol": sym, "weight": float(p["value"]) / total_value})

            # Double exposure: direct stock + ETF
            for etf in etf_positions:
                for stock in stock_positions:
                    etf_contrib = etf["weight"] * etf["constituents"].get(stock["symbol"], 0)
                    effective = stock["weight"] + etf_contrib
                    if etf_contrib > 0 and effective > stock["weight"] * 1.15:
                        warnings.append({
                            "type": "double_exposure",
                            "symbol": stock["symbol"],
                            "etf": etf["symbol"],
                            "direct_pct": round(stock["weight"] * 100, 1),
                            "etf_contribution_pct": round(etf_contrib * 100, 1),
                            "effective_pct": round(effective * 100, 1),
                            "message": (
                                f"Your effective {stock['symbol']} exposure is approximately {effective*100:.1f}% — "
                                f"{stock['symbol']} directly ({stock['weight']*100:.1f}%) plus "
                                f"your {etf['symbol']} position (approximately {etf_contrib*100:.1f}% {stock['symbol']} weight). "
                                "This may be higher than intended. This is informational."
                            ),
                        })

            # ETF-to-ETF overlap
            for i, etf1 in enumerate(etf_positions):
                for etf2 in etf_positions[i+1:]:
                    s1 = set(etf1["constituents"].keys())
                    s2 = set(etf2["constituents"].keys())
                    if not s1 or not s2:
                        continue
                    intersection = s1.intersection(s2)
                    union = s1.union(s2)
                    jaccard = len(intersection) / len(union) if union else 0
                    if jaccard > 0.35:
                        warnings.append({
                            "type": "etf_overlap",
                            "etf1": etf1["symbol"],
                            "etf2": etf2["symbol"],
                            "overlap_pct": round(jaccard * 100),
                            "message": (
                                f"{etf1['symbol']} and {etf2['symbol']} share approximately {jaccard*100:.0f}% "
                                "of holdings by weight. You may have more concentration than your position sizes suggest. "
                                "This is an estimate based on publicly available ETF data."
                            ),
                        })
        finally:
            conn.close()
    except Exception as e:
        logger.debug("calculate_etf_overlap error: %s", e)

    return warnings


def detect_cross_account_concentration(positions: list, threshold_pct: float = 0.20) -> list:
    """
    Detects same symbol held across multiple account types.
    Returns warnings when a single symbol exceeds threshold_pct of total portfolio value.
    positions: list of dicts with keys: symbol, market_value, account_type
    threshold: default 20%
    """
    from collections import defaultdict
    symbol_totals = defaultdict(lambda: {"total_value": 0.0, "accounts": set()})
    total_portfolio_value = sum(p.get("market_value", 0) for p in positions)

    if total_portfolio_value <= 0:
        return []

    for pos in positions:
        symbol = pos.get("symbol", "")
        value = pos.get("market_value", 0)
        account = pos.get("account_type", "taxable")
        symbol_totals[symbol]["total_value"] += value
        symbol_totals[symbol]["accounts"].add(account)

    warnings = []
    for symbol, data in symbol_totals.items():
        concentration = data["total_value"] / total_portfolio_value
        if len(data["accounts"]) > 1 and concentration >= threshold_pct:
            warnings.append({
                "symbol": symbol,
                "total_value": round(data["total_value"], 2),
                "concentration_pct": round(concentration * 100, 1),
                "accounts": sorted(data["accounts"]),
                "observation": (
                    f"{symbol} represents {concentration*100:.1f}% of your portfolio "
                    f"across {len(data['accounts'])} account types "
                    f"({', '.join(sorted(data['accounts']))}). "
                    "Cross-account concentration is one area worth reviewing for overall exposure."
                ),
                "severity": "info",
            })
    return sorted(warnings, key=lambda w: w["concentration_pct"], reverse=True)
