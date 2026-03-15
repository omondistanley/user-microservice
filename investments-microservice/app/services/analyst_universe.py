"""
Analyst universe: curated symbols used when the user has no holdings so recommendations
can suggest a starter portfolio. Each entry has sector/industry and risk band for
preference-aware scoring (industry match, risk-return, Sharpe alignment).
See docs/recommendations_analyst_system.md.
"""
from typing import Any, Dict, List, Optional

# Default universe: broad-market and sector ETFs plus common single names.
# Override via env ANALYST_UNIVERSE_JSON or keep this as fallback.
# Format: list of {"symbol", "sector", "risk_band", "description", "full_name", "asset_type"}
# risk_band: conservative | balanced | aggressive
# sector aligns with industry_preferences (e.g. technology, healthcare, broad_market, bonds)
# asset_type: etf | stock | crypto (for display and filtering)
DEFAULT_UNIVERSE: List[Dict[str, Any]] = [
    {"symbol": "VOO", "sector": "broad_market", "risk_band": "balanced", "description": "S&P 500", "full_name": "Vanguard S&P 500 ETF", "asset_type": "etf"},
    {"symbol": "VTI", "sector": "broad_market", "risk_band": "balanced", "description": "US total market", "full_name": "Vanguard Total Stock Market ETF", "asset_type": "etf"},
    {"symbol": "VT", "sector": "broad_market", "risk_band": "balanced", "description": "Global stock", "full_name": "Vanguard Total World Stock ETF", "asset_type": "etf"},
    {"symbol": "QQQ", "sector": "technology", "risk_band": "aggressive", "description": "Nasdaq-100", "full_name": "Invesco QQQ Trust", "asset_type": "etf"},
    {"symbol": "VXUS", "sector": "international", "risk_band": "balanced", "description": "International ex-US", "full_name": "Vanguard Total International Stock ETF", "asset_type": "etf"},
    {"symbol": "BND", "sector": "bonds", "risk_band": "conservative", "description": "Total bond", "full_name": "Vanguard Total Bond Market ETF", "asset_type": "etf"},
    {"symbol": "AGG", "sector": "bonds", "risk_band": "conservative", "description": "US aggregate bond", "full_name": "iShares Core U.S. Aggregate Bond ETF", "asset_type": "etf"},
    {"symbol": "VYM", "sector": "broad_market", "risk_band": "conservative", "description": "High dividend", "full_name": "Vanguard High Dividend Yield ETF", "asset_type": "etf"},
    {"symbol": "VUG", "sector": "technology", "risk_band": "aggressive", "description": "Growth", "full_name": "Vanguard Growth ETF", "asset_type": "etf"},
    {"symbol": "XLK", "sector": "technology", "risk_band": "aggressive", "description": "Tech sector", "full_name": "Technology Select Sector SPDR Fund", "asset_type": "etf"},
    {"symbol": "XLV", "sector": "healthcare", "risk_band": "balanced", "description": "Healthcare sector", "full_name": "Health Care Select Sector SPDR Fund", "asset_type": "etf"},
    {"symbol": "XLF", "sector": "financials", "risk_band": "balanced", "description": "Financials sector", "full_name": "Financial Select Sector SPDR Fund", "asset_type": "etf"},
    {"symbol": "VHT", "sector": "healthcare", "risk_band": "balanced", "description": "Healthcare", "full_name": "Vanguard Health Care ETF", "asset_type": "etf"},
    {"symbol": "SCHD", "sector": "broad_market", "risk_band": "conservative", "description": "Dividend growth", "full_name": "Schwab U.S. Dividend Equity ETF", "asset_type": "etf"},
]


def get_analyst_universe() -> List[Dict[str, Any]]:
    """Return the analyst universe (curated symbols for no-holdings recommendations)."""
    import os
    import json
    raw = os.environ.get("ANALYST_UNIVERSE_JSON")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return DEFAULT_UNIVERSE


def get_security_info(symbol: str) -> Optional[Dict[str, Any]]:
    """Return full_name, sector, description, asset_type for a symbol from the analyst universe, or None."""
    if not symbol or not isinstance(symbol, str):
        return None
    sym_upper = symbol.strip().upper()
    for entry in get_analyst_universe():
        if (entry.get("symbol") or "").strip().upper() == sym_upper:
            return {
                "full_name": entry.get("full_name") or entry.get("description") or sym_upper,
                "sector": (entry.get("sector") or "broad_market").replace("_", " ").title(),
                "description": entry.get("description") or "",
                "asset_type": (entry.get("asset_type") or "etf").lower(),
                "risk_band": (entry.get("risk_band") or "balanced").lower(),
            }
    return None
