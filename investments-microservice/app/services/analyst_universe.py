"""
Analyst universe: curated symbols used when the user has no holdings so recommendations
can suggest a starter portfolio. Each entry has sector/industry and risk band for
preference-aware scoring (industry match, risk-return, Sharpe alignment).
Option B/C: primary source can be security_universe table (API-sourced); fallback static list.
See docs/recommendations_analyst_system.md.
"""
import os
import json
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
    # Extended universe for ~100 recommendations (broad-market, sector, and single-name)
    {"symbol": "IVV", "sector": "broad_market", "risk_band": "balanced", "description": "S&P 500", "full_name": "iShares Core S&P 500 ETF", "asset_type": "etf"},
    {"symbol": "SPY", "sector": "broad_market", "risk_band": "balanced", "description": "S&P 500", "full_name": "SPDR S&P 500 ETF Trust", "asset_type": "etf"},
    {"symbol": "IWM", "sector": "broad_market", "risk_band": "aggressive", "description": "Russell 2000", "full_name": "iShares Russell 2000 ETF", "asset_type": "etf"},
    {"symbol": "DIA", "sector": "broad_market", "risk_band": "balanced", "description": "Dow 30", "full_name": "SPDR Dow Jones Industrial Average ETF", "asset_type": "etf"},
    {"symbol": "ITOT", "sector": "broad_market", "risk_band": "balanced", "description": "US total market", "full_name": "iShares Core S&P Total U.S. Stock Market ETF", "asset_type": "etf"},
    {"symbol": "IJR", "sector": "broad_market", "risk_band": "aggressive", "description": "S&P SmallCap 600", "full_name": "iShares Core S&P Small-Cap ETF", "asset_type": "etf"},
    {"symbol": "VB", "sector": "broad_market", "risk_band": "aggressive", "description": "Small-cap", "full_name": "Vanguard Small-Cap ETF", "asset_type": "etf"},
    {"symbol": "VO", "sector": "broad_market", "risk_band": "balanced", "description": "Mid-cap", "full_name": "Vanguard Mid-Cap ETF", "asset_type": "etf"},
    {"symbol": "VEA", "sector": "international", "risk_band": "balanced", "description": "Developed ex-US", "full_name": "Vanguard FTSE Developed Markets ETF", "asset_type": "etf"},
    {"symbol": "IEFA", "sector": "international", "risk_band": "balanced", "description": "Developed ex-US", "full_name": "iShares Core MSCI EAFE ETF", "asset_type": "etf"},
    {"symbol": "EFA", "sector": "international", "risk_band": "balanced", "description": "EAFE", "full_name": "iShares MSCI EAFE ETF", "asset_type": "etf"},
    {"symbol": "VWO", "sector": "international", "risk_band": "aggressive", "description": "Emerging markets", "full_name": "Vanguard FTSE Emerging Markets ETF", "asset_type": "etf"},
    {"symbol": "IEMG", "sector": "international", "risk_band": "aggressive", "description": "Emerging markets", "full_name": "iShares Core MSCI Emerging Markets ETF", "asset_type": "etf"},
    {"symbol": "VIG", "sector": "broad_market", "risk_band": "conservative", "description": "Dividend appreciation", "full_name": "Vanguard Dividend Appreciation ETF", "asset_type": "etf"},
    {"symbol": "DVY", "sector": "broad_market", "risk_band": "conservative", "description": "High dividend", "full_name": "iShares Select Dividend ETF", "asset_type": "etf"},
    {"symbol": "HDV", "sector": "broad_market", "risk_band": "conservative", "description": "High dividend", "full_name": "iShares Core High Dividend ETF", "asset_type": "etf"},
    {"symbol": "VTV", "sector": "broad_market", "risk_band": "conservative", "description": "Value", "full_name": "Vanguard Value ETF", "asset_type": "etf"},
    {"symbol": "IWD", "sector": "broad_market", "risk_band": "balanced", "description": "Russell 1000 value", "full_name": "iShares Russell 1000 Value ETF", "asset_type": "etf"},
    {"symbol": "IWF", "sector": "broad_market", "risk_band": "aggressive", "description": "Russell 1000 growth", "full_name": "iShares Russell 1000 Growth ETF", "asset_type": "etf"},
    {"symbol": "VGT", "sector": "technology", "risk_band": "aggressive", "description": "Tech", "full_name": "Vanguard Information Technology ETF", "asset_type": "etf"},
    {"symbol": "IYW", "sector": "technology", "risk_band": "aggressive", "description": "Tech", "full_name": "iShares U.S. Technology ETF", "asset_type": "etf"},
    {"symbol": "SOXX", "sector": "technology", "risk_band": "aggressive", "description": "Semiconductors", "full_name": "iShares Semiconductor ETF", "asset_type": "etf"},
    {"symbol": "SMH", "sector": "technology", "risk_band": "aggressive", "description": "Semiconductors", "full_name": "VanEck Semiconductor ETF", "asset_type": "etf"},
    {"symbol": "IGV", "sector": "technology", "risk_band": "aggressive", "description": "Software", "full_name": "iShares Expanded Tech-Software Sector ETF", "asset_type": "etf"},
    {"symbol": "XLE", "sector": "energy", "risk_band": "aggressive", "description": "Energy sector", "full_name": "Energy Select Sector SPDR Fund", "asset_type": "etf"},
    {"symbol": "VDE", "sector": "energy", "risk_band": "aggressive", "description": "Energy", "full_name": "Vanguard Energy ETF", "asset_type": "etf"},
    {"symbol": "XLY", "sector": "consumer", "risk_band": "aggressive", "description": "Consumer discretionary", "full_name": "Consumer Discretionary Select Sector SPDR", "asset_type": "etf"},
    {"symbol": "XLP", "sector": "consumer", "risk_band": "conservative", "description": "Consumer staples", "full_name": "Consumer Staples Select Sector SPDR", "asset_type": "etf"},
    {"symbol": "XLI", "sector": "industrial", "risk_band": "balanced", "description": "Industrials", "full_name": "Industrial Select Sector SPDR Fund", "asset_type": "etf"},
    {"symbol": "XLU", "sector": "utilities", "risk_band": "conservative", "description": "Utilities", "full_name": "Utilities Select Sector SPDR Fund", "asset_type": "etf"},
    {"symbol": "VNQ", "sector": "real_estate", "risk_band": "balanced", "description": "REITs", "full_name": "Vanguard Real Estate ETF", "asset_type": "etf"},
    {"symbol": "IYR", "sector": "real_estate", "risk_band": "balanced", "description": "REITs", "full_name": "iShares U.S. Real Estate ETF", "asset_type": "etf"},
    {"symbol": "LQD", "sector": "bonds", "risk_band": "conservative", "description": "Investment-grade corporate", "full_name": "iShares iBoxx Investment Grade Corporate Bond ETF", "asset_type": "etf"},
    {"symbol": "HYG", "sector": "bonds", "risk_band": "balanced", "description": "High-yield corporate", "full_name": "iShares iBoxx High Yield Corporate Bond ETF", "asset_type": "etf"},
    {"symbol": "BNDX", "sector": "bonds", "risk_band": "conservative", "description": "International bonds", "full_name": "Vanguard Total International Bond ETF", "asset_type": "etf"},
    {"symbol": "VGSH", "sector": "bonds", "risk_band": "conservative", "description": "Short-term Treasury", "full_name": "Vanguard Short-Term Treasury ETF", "asset_type": "etf"},
    {"symbol": "VGLT", "sector": "bonds", "risk_band": "conservative", "description": "Long-term Treasury", "full_name": "Vanguard Long-Term Treasury ETF", "asset_type": "etf"},
    {"symbol": "TLT", "sector": "bonds", "risk_band": "conservative", "description": "Long-term Treasury", "full_name": "iShares 20+ Year Treasury Bond ETF", "asset_type": "etf"},
    {"symbol": "SHY", "sector": "bonds", "risk_band": "conservative", "description": "Short-term Treasury", "full_name": "iShares 1-3 Year Treasury Bond ETF", "asset_type": "etf"},
    {"symbol": "GLD", "sector": "commodities", "risk_band": "balanced", "description": "Gold", "full_name": "SPDR Gold Shares", "asset_type": "etf"},
    {"symbol": "IAU", "sector": "commodities", "risk_band": "balanced", "description": "Gold", "full_name": "iShares Gold Trust", "asset_type": "etf"},
    {"symbol": "SLV", "sector": "commodities", "risk_band": "aggressive", "description": "Silver", "full_name": "iShares Silver Trust", "asset_type": "etf"},
    # Single-name stocks (diversified sectors)
    {"symbol": "AAPL", "sector": "technology", "risk_band": "aggressive", "description": "Apple Inc", "full_name": "Apple Inc", "asset_type": "stock"},
    {"symbol": "MSFT", "sector": "technology", "risk_band": "aggressive", "description": "Microsoft", "full_name": "Microsoft Corporation", "asset_type": "stock"},
    {"symbol": "GOOGL", "sector": "technology", "risk_band": "aggressive", "description": "Alphabet (Google)", "full_name": "Alphabet Inc Class A", "asset_type": "stock"},
    {"symbol": "AMZN", "sector": "technology", "risk_band": "aggressive", "description": "Amazon", "full_name": "Amazon.com Inc", "asset_type": "stock"},
    {"symbol": "NVDA", "sector": "technology", "risk_band": "aggressive", "description": "NVIDIA", "full_name": "NVIDIA Corporation", "asset_type": "stock"},
    {"symbol": "META", "sector": "technology", "risk_band": "aggressive", "description": "Meta Platforms", "full_name": "Meta Platforms Inc", "asset_type": "stock"},
    {"symbol": "TSLA", "sector": "technology", "risk_band": "aggressive", "description": "Tesla", "full_name": "Tesla Inc", "asset_type": "stock"},
    {"symbol": "JPM", "sector": "financials", "risk_band": "balanced", "description": "JPMorgan Chase", "full_name": "JPMorgan Chase & Co", "asset_type": "stock"},
    {"symbol": "V", "sector": "financials", "risk_band": "balanced", "description": "Visa", "full_name": "Visa Inc Class A", "asset_type": "stock"},
    {"symbol": "MA", "sector": "financials", "risk_band": "balanced", "description": "Mastercard", "full_name": "Mastercard Inc", "asset_type": "stock"},
    {"symbol": "BAC", "sector": "financials", "risk_band": "balanced", "description": "Bank of America", "full_name": "Bank of America Corp", "asset_type": "stock"},
    {"symbol": "WFC", "sector": "financials", "risk_band": "balanced", "description": "Wells Fargo", "full_name": "Wells Fargo & Company", "asset_type": "stock"},
    {"symbol": "JNJ", "sector": "healthcare", "risk_band": "balanced", "description": "Johnson & Johnson", "full_name": "Johnson & Johnson", "asset_type": "stock"},
    {"symbol": "UNH", "sector": "healthcare", "risk_band": "balanced", "description": "UnitedHealth", "full_name": "UnitedHealth Group Inc", "asset_type": "stock"},
    {"symbol": "PFE", "sector": "healthcare", "risk_band": "balanced", "description": "Pfizer", "full_name": "Pfizer Inc", "asset_type": "stock"},
    {"symbol": "ABBV", "sector": "healthcare", "risk_band": "balanced", "description": "AbbVie", "full_name": "AbbVie Inc", "asset_type": "stock"},
    {"symbol": "XOM", "sector": "energy", "risk_band": "aggressive", "description": "Exxon Mobil", "full_name": "Exxon Mobil Corporation", "asset_type": "stock"},
    {"symbol": "CVX", "sector": "energy", "risk_band": "aggressive", "description": "Chevron", "full_name": "Chevron Corporation", "asset_type": "stock"},
    {"symbol": "KO", "sector": "consumer", "risk_band": "conservative", "description": "Coca-Cola", "full_name": "Coca-Cola Company", "asset_type": "stock"},
    {"symbol": "PEP", "sector": "consumer", "risk_band": "conservative", "description": "PepsiCo", "full_name": "PepsiCo Inc", "asset_type": "stock"},
    {"symbol": "WMT", "sector": "consumer", "risk_band": "conservative", "description": "Walmart", "full_name": "Walmart Inc", "asset_type": "stock"},
    {"symbol": "PG", "sector": "consumer", "risk_band": "conservative", "description": "Procter & Gamble", "full_name": "Procter & Gamble Co", "asset_type": "stock"},
    {"symbol": "HD", "sector": "consumer", "risk_band": "balanced", "description": "Home Depot", "full_name": "Home Depot Inc", "asset_type": "stock"},
    {"symbol": "MCD", "sector": "consumer", "risk_band": "conservative", "description": "McDonald's", "full_name": "McDonald's Corporation", "asset_type": "stock"},
    {"symbol": "DIS", "sector": "consumer", "risk_band": "aggressive", "description": "Walt Disney", "full_name": "Walt Disney Company", "asset_type": "stock"},
    {"symbol": "NKE", "sector": "consumer", "risk_band": "aggressive", "description": "Nike", "full_name": "Nike Inc", "asset_type": "stock"},
    {"symbol": "COST", "sector": "consumer", "risk_band": "balanced", "description": "Costco", "full_name": "Costco Wholesale Corporation", "asset_type": "stock"},
    {"symbol": "BRK.B", "sector": "financials", "risk_band": "balanced", "description": "Berkshire Hathaway", "full_name": "Berkshire Hathaway Inc Class B", "asset_type": "stock"},
    {"symbol": "CRM", "sector": "technology", "risk_band": "aggressive", "description": "Salesforce", "full_name": "Salesforce Inc", "asset_type": "stock"},
    {"symbol": "ORCL", "sector": "technology", "risk_band": "balanced", "description": "Oracle", "full_name": "Oracle Corporation", "asset_type": "stock"},
    {"symbol": "ADBE", "sector": "technology", "risk_band": "aggressive", "description": "Adobe", "full_name": "Adobe Inc", "asset_type": "stock"},
    {"symbol": "INTC", "sector": "technology", "risk_band": "aggressive", "description": "Intel", "full_name": "Intel Corporation", "asset_type": "stock"},
    {"symbol": "AMD", "sector": "technology", "risk_band": "aggressive", "description": "AMD", "full_name": "Advanced Micro Devices Inc", "asset_type": "stock"},
    {"symbol": "AVGO", "sector": "technology", "risk_band": "aggressive", "description": "Broadcom", "full_name": "Broadcom Inc", "asset_type": "stock"},
    {"symbol": "QCOM", "sector": "technology", "risk_band": "aggressive", "description": "Qualcomm", "full_name": "Qualcomm Inc", "asset_type": "stock"},
    {"symbol": "TXN", "sector": "technology", "risk_band": "balanced", "description": "Texas Instruments", "full_name": "Texas Instruments Inc", "asset_type": "stock"},
    {"symbol": "IBM", "sector": "technology", "risk_band": "balanced", "description": "IBM", "full_name": "International Business Machines Corp", "asset_type": "stock"},
    {"symbol": "CSCO", "sector": "technology", "risk_band": "balanced", "description": "Cisco", "full_name": "Cisco Systems Inc", "asset_type": "stock"},
    {"symbol": "NFLX", "sector": "technology", "risk_band": "aggressive", "description": "Netflix", "full_name": "Netflix Inc", "asset_type": "stock"},
    {"symbol": "PM", "sector": "consumer", "risk_band": "conservative", "description": "Philip Morris", "full_name": "Philip Morris International Inc", "asset_type": "stock"},
    {"symbol": "MO", "sector": "consumer", "risk_band": "conservative", "description": "Altria", "full_name": "Altria Group Inc", "asset_type": "stock"},
    {"symbol": "T", "sector": "technology", "risk_band": "conservative", "description": "AT&T", "full_name": "AT&T Inc", "asset_type": "stock"},
    {"symbol": "VZ", "sector": "technology", "risk_band": "conservative", "description": "Verizon", "full_name": "Verizon Communications Inc", "asset_type": "stock"},
    {"symbol": "MRK", "sector": "healthcare", "risk_band": "balanced", "description": "Merck", "full_name": "Merck & Co Inc", "asset_type": "stock"},
    {"symbol": "LLY", "sector": "healthcare", "risk_band": "aggressive", "description": "Eli Lilly", "full_name": "Eli Lilly and Company", "asset_type": "stock"},
    {"symbol": "TMO", "sector": "healthcare", "risk_band": "balanced", "description": "Thermo Fisher", "full_name": "Thermo Fisher Scientific Inc", "asset_type": "stock"},
    {"symbol": "ABT", "sector": "healthcare", "risk_band": "balanced", "description": "Abbott", "full_name": "Abbott Laboratories", "asset_type": "stock"},
    {"symbol": "DHR", "sector": "healthcare", "risk_band": "balanced", "description": "Danaher", "full_name": "Danaher Corporation", "asset_type": "stock"},
    {"symbol": "BMY", "sector": "healthcare", "risk_band": "balanced", "description": "Bristol-Myers Squibb", "full_name": "Bristol-Myers Squibb Company", "asset_type": "stock"},
    {"symbol": "AMGN", "sector": "healthcare", "risk_band": "balanced", "description": "Amgen", "full_name": "Amgen Inc", "asset_type": "stock"},
    {"symbol": "GILD", "sector": "healthcare", "risk_band": "balanced", "description": "Gilead", "full_name": "Gilead Sciences Inc", "asset_type": "stock"},
    {"symbol": "LMT", "sector": "industrial", "risk_band": "balanced", "description": "Lockheed Martin", "full_name": "Lockheed Martin Corporation", "asset_type": "stock"},
    {"symbol": "UNP", "sector": "industrial", "risk_band": "balanced", "description": "Union Pacific", "full_name": "Union Pacific Corporation", "asset_type": "stock"},
    {"symbol": "UPS", "sector": "industrial", "risk_band": "balanced", "description": "UPS", "full_name": "United Parcel Service Inc", "asset_type": "stock"},
    {"symbol": "HON", "sector": "industrial", "risk_band": "balanced", "description": "Honeywell", "full_name": "Honeywell International Inc", "asset_type": "stock"},
    {"symbol": "CAT", "sector": "industrial", "risk_band": "aggressive", "description": "Caterpillar", "full_name": "Caterpillar Inc", "asset_type": "stock"},
    {"symbol": "DE", "sector": "industrial", "risk_band": "balanced", "description": "Deere", "full_name": "Deere & Company", "asset_type": "stock"},
    {"symbol": "BA", "sector": "industrial", "risk_band": "aggressive", "description": "Boeing", "full_name": "Boeing Company", "asset_type": "stock"},
    {"symbol": "GE", "sector": "industrial", "risk_band": "aggressive", "description": "General Electric", "full_name": "General Electric Company", "asset_type": "stock"},
    {"symbol": "RTX", "sector": "industrial", "risk_band": "balanced", "description": "RTX Corp", "full_name": "RTX Corp", "asset_type": "stock"},
]


def _get_static_universe() -> List[Dict[str, Any]]:
    """Return static list only (env ANALYST_UNIVERSE_JSON or DEFAULT_UNIVERSE)."""
    raw = os.environ.get("ANALYST_UNIVERSE_JSON")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return DEFAULT_UNIVERSE


# ---------------------------------------------------------------------------
# ETF overlap deduplication (Sprint 1)
# ---------------------------------------------------------------------------
# Groups of ETFs that are substantially identical (track the same index or
# near-identical index with > ~90% overlap).  When multiple members of a group
# appear in the universe list, we keep only the first one encountered so the
# recommendation engine does not surface redundant suggestions.
#
# Ordering within each group matters: the *first* symbol is the preferred
# representative (lowest cost, highest liquidity, broadest adoption).
# ---------------------------------------------------------------------------
HIGH_OVERLAP_GROUPS: List[List[str]] = [
    # S&P 500
    ["VOO", "IVV", "SPY", "SPLG", "CSPX"],
    # US total market
    ["VTI", "ITOT", "SPTM", "SCHB"],
    # Emerging markets
    ["VWO", "IEMG", "EEM"],
    # Developed ex-US (EAFE-family)
    ["VEA", "IEFA", "EFA", "SCHF"],
    # Semiconductors
    ["SOXX", "SMH"],
    # US total bond
    ["BND", "AGG", "SCHZ"],
    # High dividend
    ["VYM", "HDV", "DVY"],
    # Technology
    ["VGT", "XLK", "IYW"],
    # Healthcare
    ["VHT", "XLV"],
    # US growth
    ["VUG", "IWF", "SCHG"],
    # US value
    ["VTV", "IWD", "SCHV"],
    # Real estate
    ["VNQ", "IYR", "SCHH"],
    # Clean energy
    ["ICLN", "QCLN"],
    # Energy sector
    ["XLE", "VDE"],
    # Financial sector
    ["XLF", "VFH"],
]

# Build a fast lookup: symbol → preferred representative in its group
_OVERLAP_PREFERRED: Dict[str, str] = {}
for _group in HIGH_OVERLAP_GROUPS:
    _preferred = _group[0]
    for _sym in _group[1:]:
        _OVERLAP_PREFERRED[_sym] = _preferred


def deduplicate_universe(universe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove ETFs that are substantially identical to another already-included entry.

    Logic: iterate in order; if a symbol is a non-preferred member of an overlap
    group AND the preferred representative for that group is already in the list,
    drop the duplicate.  This keeps the preferred ticker and discards the rest.

    Result: cleaner suggestions — the user sees "VOO" once, not "VOO + IVV + SPY".
    """
    seen_symbols: set = set()
    seen_preferred: set = set()
    result: List[Dict[str, Any]] = []

    for entry in universe:
        sym = (entry.get("symbol") or "").strip().upper()
        if not sym:
            continue
        preferred = _OVERLAP_PREFERRED.get(sym)
        if preferred is not None:
            # This symbol is a non-preferred duplicate; skip if preferred is already included
            if preferred in seen_preferred or preferred in seen_symbols:
                continue
        if sym not in seen_symbols:
            seen_symbols.add(sym)
            if preferred is None:
                # This symbol is either a preferred rep or not in any overlap group
                seen_preferred.add(sym)
            result.append(entry)

    return result


def get_analyst_universe() -> List[Dict[str, Any]]:
    """Return the analyst universe, deduplicated for ETF overlap. Prefer security_universe table if populated (Option C); else static list."""
    try:
        from app.services.service_factory import ServiceFactory
        universe_svc = ServiceFactory.get_service("UniverseDataService")
        if universe_svc is not None:
            from app.core.config import MAX_RECOMMENDATIONS
            rows = universe_svc.list_universe(limit=MAX_RECOMMENDATIONS or 500)
            if rows:
                return deduplicate_universe(rows)
    except Exception:
        pass
    return deduplicate_universe(_get_static_universe())


def get_security_info(symbol: str) -> Optional[Dict[str, Any]]:
    """Return full_name, sector, description, asset_type for a symbol. Static list -> DB -> on-demand resolve (Option B)."""
    if not symbol or not isinstance(symbol, str):
        return None
    sym_upper = symbol.strip().upper()
    # 1) Static list
    for entry in _get_static_universe():
        if (entry.get("symbol") or "").strip().upper() == sym_upper:
            return {
                "full_name": entry.get("full_name") or entry.get("description") or sym_upper,
                "sector": (entry.get("sector") or "broad_market").replace("_", " ").title(),
                "description": entry.get("description") or "",
                "asset_type": (entry.get("asset_type") or "etf").lower(),
                "risk_band": (entry.get("risk_band") or "balanced").lower(),
            }
    # 2) DB cache (security_universe)
    try:
        from app.services.service_factory import ServiceFactory
        universe_svc = ServiceFactory.get_service("UniverseDataService")
        if universe_svc is not None:
            row = universe_svc.get_by_symbol(sym_upper)
            if row is not None:
                return row
    except Exception:
        pass
    # 3) On-demand resolve and cache (Option B)
    try:
        from app.services.security_metadata_resolver import resolve_security_metadata
        from app.services.universe_metadata_mapper import canonical_to_db_row
        canonical = resolve_security_metadata(sym_upper)
        if canonical is not None:
            from app.services.service_factory import ServiceFactory
            universe_svc = ServiceFactory.get_service("UniverseDataService")
            if universe_svc is not None:
                row = canonical_to_db_row(canonical, "on_demand")
                universe_svc.upsert(
                    symbol=row["symbol"],
                    full_name=row["full_name"],
                    sector=row["sector"],
                    risk_band=row["risk_band"],
                    description=row["description"],
                    asset_type=row["asset_type"],
                    source_provider=row["source_provider"],
                )
            sector_display = (canonical.get("sector") or "broad_market").replace("_", " ").title()
            return {
                "full_name": canonical.get("full_name") or sym_upper,
                "sector": sector_display,
                "description": canonical.get("description") or "",
                "asset_type": (canonical.get("asset_type") or "stock").lower(),
                "risk_band": (canonical.get("risk_band") or "balanced").lower(),
            }
    except Exception:
        pass
    return None
