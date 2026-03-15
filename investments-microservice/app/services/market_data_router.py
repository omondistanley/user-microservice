"""Market data router: selects first healthy provider from configured order."""
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import (
    MARKET_DATA_PROVIDER_ORDER,
    MARKET_PROVIDER_STATUS_CACHE_SECONDS,
    MARKET_QUOTE_DEVIATION_PCT,
    QUOTE_CACHE_MAX_AGE_SECONDS,
)
from app.services.alphavantage_adapter import AlphaVantageAdapter
from app.services.alpaca_adapter import AlpacaAdapter
from app.services.finnhub_adapter import FinnhubAdapter
from app.services.free_adapter import FreeAdapter
from app.services.market_data_adapter import MarketDataAdapter
from app.services.market_data_models import Bar, Quote
from app.services.twelvedata_adapter import TwelveDataAdapter

logger = logging.getLogger("investments_market_router")

# In-memory quote cache: symbol -> (Quote, fetched_at_timestamp)
_quote_cache: Dict[str, Tuple[Quote, float]] = {}
# Provider status cache: (list of status dicts, cached_at_timestamp) or None
_status_cache: Optional[Tuple[List[Dict], float]] = None


class MarketDataRouter:
    """Routing facade that selects the best provider and exposes a simple API."""

    def __init__(
        self,
        alpaca: Optional[MarketDataAdapter] = None,
        free: Optional[MarketDataAdapter] = None,
        finnhub: Optional[MarketDataAdapter] = None,
        twelvedata: Optional[MarketDataAdapter] = None,
        alphavantage: Optional[MarketDataAdapter] = None,
    ) -> None:
        self._alpaca = alpaca or AlpacaAdapter()
        self._free = free or FreeAdapter()
        self._finnhub = finnhub or FinnhubAdapter()
        self._twelvedata = twelvedata or TwelveDataAdapter()
        self._alphavantage = alphavantage or AlphaVantageAdapter()
        order = [p.strip() for p in (MARKET_DATA_PROVIDER_ORDER or "").split(",") if p.strip()]
        self._order = order or ["alpaca", "finnhub", "twelvedata", "alphavantage"]

    def _get_adapter(self, name: str) -> Optional[MarketDataAdapter]:
        name = (name or "").lower()
        if name == "alpaca":
            return self._alpaca
        if name == "free":
            return self._free
        if name == "finnhub":
            return self._finnhub
        if name == "twelvedata":
            return self._twelvedata
        if name == "alphavantage":
            return self._alphavantage
        return None

    async def get_quote(self, symbol: str) -> Quote:
        quote, _, _ = await self.get_quote_with_meta(symbol)
        return quote

    async def get_quote_with_meta(
        self, symbol: str
    ) -> Tuple[Quote, bool, Optional[Dict[str, Any]]]:
        """Return (quote, fallback_used, provenance). provenance may include data_quality."""
        sym = symbol.upper()
        now_ts = time.time()
        # Cache-first: return cached quote if fresh
        if QUOTE_CACHE_MAX_AGE_SECONDS > 0 and sym in _quote_cache:
            cached_quote, fetched_at = _quote_cache[sym]
            if now_ts - fetched_at <= QUOTE_CACHE_MAX_AGE_SECONDS:
                return cached_quote, False, {"from_cache": True}

        last_error: Optional[Exception] = None
        for idx, name in enumerate(self._order):
            adapter = self._get_adapter(name)
            if adapter is None:
                continue
            try:
                quote = await adapter.get_quote(symbol)
                # Discrepancy check: compare to last known price
                provenance: Optional[Dict[str, Any]] = None
                if sym in _quote_cache:
                    old_quote, _ = _quote_cache[sym]
                    old_price = old_quote.price
                    new_price = quote.price
                    if old_price and old_price > 0:
                        pct = abs(float(new_price - old_price) / float(old_price))
                        if pct > MARKET_QUOTE_DEVIATION_PCT:
                            logger.warning(
                                "market_quote_discrepancy",
                                extra={
                                    "symbol": sym,
                                    "provider": quote.provider,
                                    "old_price": str(old_price),
                                    "new_price": str(new_price),
                                    "pct": pct,
                                },
                            )
                            provenance = {"data_quality": "discrepancy_detected", "pct_change": round(pct, 4)}
                # Update cache
                _quote_cache[sym] = (quote, now_ts)
                return quote, idx > 0, provenance
            except Exception as exc:
                last_error = exc
                logger.debug("market_data_provider_failed", extra={"provider": name, "error": str(exc)})
                continue
        if last_error:
            raise last_error
        raise RuntimeError("No market data providers configured")

    async def get_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[Bar]:
        last_error: Optional[Exception] = None
        for idx, name in enumerate(self._order):
            adapter = self._get_adapter(name)
            if adapter is None:
                continue
            try:
                bars = await adapter.get_bars(symbol, interval, start, end)
                if bars:
                    return bars
            except Exception as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        return []

    async def get_provider_statuses(self) -> List[Dict]:
        """Return status for each known provider (health cache applied)."""
        global _status_cache
        now_ts = time.time()
        if (
            _status_cache is not None
            and now_ts - _status_cache[1] < MARKET_PROVIDER_STATUS_CACHE_SECONDS
        ):
            return _status_cache[0]
        from app.services.market_data_models import ProviderStatus

        result: List[Dict] = []
        for name in ("alpaca", "free", "finnhub", "twelvedata", "alphavantage"):
            adapter = self._get_adapter(name)
            if adapter is None:
                continue
            try:
                status = await adapter.status()
                result.append(status.model_dump())
            except Exception:
                result.append(
                    ProviderStatus(provider=name, status="down").model_dump()
                )
        _status_cache = (result, now_ts)
        return result


def get_default_market_data_router() -> MarketDataRouter:
    return MarketDataRouter()
