"""
Analyst universe: curated symbols used when the user has no holdings so recommendations
can suggest a starter portfolio. Each entry has sector/industry and risk band for
preference-aware scoring (industry match, risk-return, Sharpe alignment).
See docs/recommendations_analyst_system.md.
"""
from typing import Any, Dict, List

# Default universe: broad-market and sector ETFs plus common single names.
# Override via env ANALYST_UNIVERSE_JSON or keep this as fallback.
# Format: list of {"symbol", "sector", "risk_band", "description"}
# risk_band: conservative | balanced | aggressive
# sector aligns with industry_preferences (e.g. technology, healthcare, broad_market, bonds)
DEFAULT_UNIVERSE: List[Dict[str, Any]] = [
    {"symbol": "VOO", "sector": "broad_market", "risk_band": "balanced", "description": "S&P 500"},
    {"symbol": "VTI", "sector": "broad_market", "risk_band": "balanced", "description": "US total market"},
    {"symbol": "VT", "sector": "broad_market", "risk_band": "balanced", "description": "Global stock"},
    {"symbol": "QQQ", "sector": "technology", "risk_band": "aggressive", "description": "Nasdaq-100"},
    {"symbol": "VXUS", "sector": "international", "risk_band": "balanced", "description": "International ex-US"},
    {"symbol": "BND", "sector": "bonds", "risk_band": "conservative", "description": "Total bond"},
    {"symbol": "AGG", "sector": "bonds", "risk_band": "conservative", "description": "US aggregate bond"},
    {"symbol": "VYM", "sector": "broad_market", "risk_band": "conservative", "description": "High dividend"},
    {"symbol": "VUG", "sector": "technology", "risk_band": "aggressive", "description": "Growth"},
    {"symbol": "XLK", "sector": "technology", "risk_band": "aggressive", "description": "Tech sector"},
    {"symbol": "XLV", "sector": "healthcare", "risk_band": "balanced", "description": "Healthcare sector"},
    {"symbol": "XLF", "sector": "financials", "risk_band": "balanced", "description": "Financials sector"},
    {"symbol": "VHT", "sector": "healthcare", "risk_band": "balanced", "description": "Healthcare"},
    {"symbol": "SCHD", "sector": "broad_market", "risk_band": "conservative", "description": "Dividend growth"},
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
