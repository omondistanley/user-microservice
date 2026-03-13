from datetime import datetime, timezone
from typing import List, Optional

from app.core.config import MARKET_DATA_PROVIDER_ORDER
from .alpaca_adapter import AlpacaAdapter
from .free_adapter import FreeAdapter
from .market_data_adapter import MarketDataAdapter
from .market_data_models import Bar, Quote


class MarketDataRouter:
    """Routing facade that selects the best provider and exposes a simple API."""

    def __init__(
        self,
        alpaca: Optional[MarketDataAdapter] = None,
        free: Optional[MarketDataAdapter] = None,
    ) -> None:
        self._alpaca = alpaca or AlpacaAdapter()
        self._free = free or FreeAdapter()
        order = [p.strip() for p in (MARKET_DATA_PROVIDER_ORDER or "").split(",") if p.strip()]
        # default preference: alpaca, then free
        self._order = order or ["alpaca", "free"]

    async def get_quote(self, symbol: str) -> Quote:
        last_error: Optional[Exception] = None
        for name in self._order:
            adapter = self._get_adapter(name)
            if adapter is None:
                continue
            try:
                return await adapter.get_quote(symbol)
            except Exception as exc:  # pragma: no cover - exercised via integration tests
                last_error = exc
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
        for name in self._order:
            adapter = self._get_adapter(name)
            if adapter is None:
                continue
            try:
                bars = await adapter.get_bars(symbol, interval, start, end)
                if bars:
                    return bars
            except Exception as exc:  # pragma: no cover
                last_error = exc
                continue
        if last_error:
            raise last_error
        return []

    def _get_adapter(self, name: str) -> Optional[MarketDataAdapter]:
        name = (name or "").lower()
        if name == "alpaca":
            return self._alpaca
        if name == "free":
            return self._free
        return None


def get_default_market_data_router() -> MarketDataRouter:
    # Simple factory for dependency injection
    return MarketDataRouter()

