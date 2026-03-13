from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from .market_data_models import Bar, ProviderStatus, Quote


class MarketDataAdapter(ABC):
    """Abstract interface for market data providers."""

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        raise NotImplementedError()

    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[Bar]:
        raise NotImplementedError()

    @abstractmethod
    async def search_symbol(self, query: str) -> list[dict]:
        """Optional symbol search. Implementations may return an empty list."""
        raise NotImplementedError()

    @abstractmethod
    async def status(self) -> ProviderStatus:
        raise NotImplementedError()

