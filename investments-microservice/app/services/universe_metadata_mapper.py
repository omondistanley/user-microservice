"""
Map Finnhub and Alpha Vantage company/profile payloads to canonical security metadata.
Used by bootstrap and on-demand resolver; single place for sector/risk_band logic.
"""
from typing import Any, Dict, Optional

# Our normalized sectors (align with industry_preferences and analyst_universe)
CANONICAL_SECTORS = {
    "technology", "healthcare", "financials", "consumer", "energy", "industrial",
    "utilities", "real_estate", "bonds", "international", "broad_market", "commodities",
}

# Map provider industry/sector strings (lower, normalized) to canonical sector
INDUSTRY_TO_SECTOR: Dict[str, str] = {
    "technology": "technology",
    "tech": "technology",
    "software": "technology",
    "information technology": "technology",
    "healthcare": "healthcare",
    "health care": "healthcare",
    "pharmaceuticals": "healthcare",
    "biotechnology": "healthcare",
    "financials": "financials",
    "financial services": "financials",
    "banks": "financials",
    "consumer": "consumer",
    "consumer discretionary": "consumer",
    "consumer staples": "consumer",
    "consumer cyclicals": "consumer",
    "energy": "energy",
    "oil": "energy",
    "industrial": "industrial",
    "industrials": "industrial",
    "utilities": "utilities",
    "real estate": "real_estate",
    "reit": "real_estate",
    "real estate investment trust": "real_estate",
    "bonds": "bonds",
    "fixed income": "bonds",
    "etf": "broad_market",
    "commodities": "commodities",
    "precious metals": "commodities",
    "materials": "commodities",
}


def _normalize_industry(s: Optional[str]) -> str:
    if not s or not isinstance(s, str):
        return "broad_market"
    key = s.strip().lower().replace(" ", "_").replace("-", "_")
    if key in INDUSTRY_TO_SECTOR:
        return INDUSTRY_TO_SECTOR[key]
    for prefix, sector in INDUSTRY_TO_SECTOR.items():
        if prefix in key or key in prefix:
            return sector
    return "broad_market"


def _infer_risk_band(
    asset_type: Optional[str] = None,
    sector: Optional[str] = None,
    market_cap: Optional[float] = None,
) -> str:
    if asset_type:
        at = asset_type.lower()
        if "bond" in at or "income" in at or "fixed" in at:
            return "conservative"
        if "crypto" in at:
            return "aggressive"
    if sector and sector.lower() in ("bonds", "utilities"):
        return "conservative"
    if market_cap is not None:
        if market_cap >= 10_000_000_000:  # 10B+
            return "balanced"
        if market_cap < 2_000_000_000:  # <2B
            return "aggressive"
    return "balanced"


def _normalize_asset_type(provider_type: Optional[str]) -> str:
    if not provider_type:
        return "stock"
    t = provider_type.strip().lower()
    if "etf" in t or "fund" in t:
        return "etf"
    if "crypto" in t:
        return "crypto"
    return "stock"


def map_finnhub_profile_to_canonical(data: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """Convert Finnhub profile2 response to canonical security metadata."""
    if not data or not isinstance(data, dict):
        return _empty_canonical(symbol)
    name = data.get("name") or data.get("ticker") or symbol
    industry = data.get("finnhubIndustry") or data.get("industry") or ""
    desc = data.get("description") or ""
    if isinstance(desc, str) and len(desc) > 2000:
        desc = desc[:2000] + "..."
    sector = _normalize_industry(industry or data.get("finnhubIndustry"))
    market_cap = None
    if "marketCapitalization" in data and data["marketCapitalization"] is not None:
        try:
            market_cap = float(data["marketCapitalization"])
        except (TypeError, ValueError):
            pass
    asset_type = _normalize_asset_type(data.get("type"))
    risk_band = _infer_risk_band(asset_type=asset_type, sector=sector, market_cap=market_cap)
    return {
        "symbol": symbol.upper(),
        "full_name": name,
        "sector": sector,
        "risk_band": risk_band,
        "description": desc or name,
        "asset_type": asset_type,
    }


def map_alphavantage_overview_to_canonical(data: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """Convert Alpha Vantage OVERVIEW response to canonical security metadata."""
    if not data or not isinstance(data, dict):
        return _empty_canonical(symbol)
    name = data.get("Name") or data.get("Symbol") or symbol
    sector = _normalize_industry(data.get("Sector") or data.get("Industry"))
    desc = data.get("Description") or ""
    if isinstance(desc, str) and len(desc) > 2000:
        desc = desc[:2000] + "..."
    asset_type = _normalize_asset_type(data.get("AssetType"))
    risk_band = _infer_risk_band(asset_type=asset_type, sector=sector)
    return {
        "symbol": symbol.upper(),
        "full_name": name,
        "sector": sector,
        "risk_band": risk_band,
        "description": desc or name,
        "asset_type": asset_type,
    }


def _empty_canonical(symbol: str) -> Dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "full_name": symbol,
        "sector": "broad_market",
        "risk_band": "balanced",
        "description": "",
        "asset_type": "stock",
    }


def canonical_to_db_row(canonical: Dict[str, Any], source_provider: str) -> Dict[str, Any]:
    """Canonical dict to kwargs for UniverseDataService.upsert."""
    return {
        "symbol": (canonical.get("symbol") or "").upper(),
        "full_name": canonical.get("full_name") or canonical.get("symbol"),
        "sector": canonical.get("sector") or "broad_market",
        "risk_band": canonical.get("risk_band") or "balanced",
        "description": canonical.get("description") or "",
        "asset_type": canonical.get("asset_type") or "stock",
        "source_provider": source_provider,
    }
