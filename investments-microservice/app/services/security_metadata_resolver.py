"""
On-demand security metadata resolution (Option B).
Calls Finnhub profile2 and Alpha Vantage OVERVIEW; returns canonical dict.
Caller is responsible for upserting into security_universe.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from app.services.alphavantage_adapter import AlphaVantageAdapter
from app.services.finnhub_adapter import FinnhubAdapter
from app.services.universe_metadata_mapper import (
    map_alphavantage_overview_to_canonical,
    map_finnhub_profile_to_canonical,
)

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async coroutine from sync context (e.g. get_security_info from recommendation engine)."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def resolve_security_metadata(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Resolve metadata for symbol from Finnhub then Alpha Vantage.
    Returns canonical dict (full_name, sector, risk_band, description, asset_type) or None.
    Caller should upsert into security_universe with source_provider='on_demand'.
    """
    if not symbol or not isinstance(symbol, str):
        return None
    sym = symbol.strip().upper()

    async def _fetch() -> Optional[Dict[str, Any]]:
        finnhub = FinnhubAdapter()
        av = AlphaVantageAdapter()
        # Try Finnhub first
        if finnhub._configured():
            try:
                profile = await finnhub.get_company_profile(sym)
                if profile:
                    canonical = map_finnhub_profile_to_canonical(profile, sym)
                    return canonical
            except Exception as e:
                logger.debug("Finnhub profile failed for %s: %s", sym, e)
        # Fallback to Alpha Vantage
        if av._configured():
            try:
                overview = await av.get_company_overview(sym)
                if overview:
                    canonical = map_alphavantage_overview_to_canonical(overview, sym)
                    return canonical
            except Exception as e:
                logger.debug("Alpha Vantage overview failed for %s: %s", sym, e)
        return None

    try:
        return _run_async(_fetch())
    except Exception as e:
        logger.warning("resolve_security_metadata failed for %s: %s", sym, e)
        return None
