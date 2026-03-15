"""
Bootstrap security_universe from Finnhub symbol list + company profiles (Option C).
Throttles to respect rate limits; optionally falls back to Alpha Vantage for failed symbols.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.alphavantage_adapter import AlphaVantageAdapter
from app.services.finnhub_adapter import FinnhubAdapter
from app.services.service_factory import ServiceFactory
from app.services.universe_data_service import UniverseDataService
from app.services.universe_metadata_mapper import (
    canonical_to_db_row,
    map_alphavantage_overview_to_canonical,
    map_finnhub_profile_to_canonical,
)

logger = logging.getLogger(__name__)

# Finnhub free tier ~60/min; throttle to ~1/sec for safety
PROFILE_DELAY_SECONDS = 1.1


def _get_universe_service() -> Optional[UniverseDataService]:
    svc = ServiceFactory.get_service("UniverseDataService")
    if isinstance(svc, UniverseDataService):
        return svc
    return None


async def run_bootstrap(
    symbol_limit: int = 500,
    exchange: str = "US",
    use_alphavantage_fallback: bool = True,
) -> Tuple[int, int, int]:
    """
    Fetch symbol list from Finnhub, then for each symbol fetch profile and upsert.
    Returns (fetched_count, upserted_count, failed_count).
    """
    finnhub = FinnhubAdapter()
    av = AlphaVantageAdapter()
    universe_svc = _get_universe_service()
    if not universe_svc:
        logger.warning("UniverseDataService not available for bootstrap")
        return 0, 0, 0
    if not finnhub._configured():
        logger.warning("Finnhub not configured; cannot bootstrap")
        return 0, 0, 0

    symbols_raw = await finnhub.list_stock_symbols(exchange)
    # Filter: prefer common stock and ETF; take up to symbol_limit
    symbols: List[str] = []
    for s in symbols_raw:
        sym = (s.get("symbol") or "").strip().upper()
        if not sym:
            continue
        t = (s.get("type") or "").lower()
        if t in ("common stock", "etf", "eps", ""):
            symbols.append(sym)
        if len(symbols) >= symbol_limit:
            break
    if not symbols:
        # If no type filter matched, take first N
        for s in symbols_raw[:symbol_limit]:
            sym = (s.get("symbol") or "").strip().upper()
            if sym:
                symbols.append(sym)

    fetched = 0
    upserted = 0
    failed = 0

    for i, sym in enumerate(symbols):
        try:
            profile = await finnhub.get_company_profile(sym)
            if profile:
                canonical = map_finnhub_profile_to_canonical(profile, sym)
                row = canonical_to_db_row(canonical, "finnhub")
                universe_svc.upsert(
                    symbol=row["symbol"],
                    full_name=row["full_name"],
                    sector=row["sector"],
                    risk_band=row["risk_band"],
                    description=row["description"],
                    asset_type=row["asset_type"],
                    source_provider=row["source_provider"],
                )
                fetched += 1
                upserted += 1
            else:
                if use_alphavantage_fallback and av._configured():
                    try:
                        overview = await av.get_company_overview(sym)
                        if overview:
                            canonical = map_alphavantage_overview_to_canonical(overview, sym)
                            row = canonical_to_db_row(canonical, "alphavantage")
                            universe_svc.upsert(
                                symbol=row["symbol"],
                                full_name=row["full_name"],
                                sector=row["sector"],
                                risk_band=row["risk_band"],
                                description=row["description"],
                                asset_type=row["asset_type"],
                                source_provider=row["source_provider"],
                            )
                            fetched += 1
                            upserted += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1
                else:
                    failed += 1
        except Exception as e:
            logger.debug("Bootstrap profile failed for %s: %s", sym, e)
            failed += 1
        if (i + 1) % 50 == 0:
            logger.info("Universe bootstrap progress: %s/%s", i + 1, len(symbols))
        await asyncio.sleep(PROFILE_DELAY_SECONDS)
    return fetched, upserted, failed
