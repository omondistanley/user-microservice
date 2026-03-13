from datetime import datetime, timezone
from typing import List

import httpx

from app.core.config import FREE_MARKET_API_KEY, FREE_MARKET_BASE_URL
from .market_data_adapter import MarketDataAdapter
from .market_data_models import Bar, ProviderStatus, Quote


class FreeAdapter(MarketDataAdapter):
    """Free-market data adapter (e.g. Finnhub/AlphaVantage/TwelveData-style APIs).

    This implementation is intentionally generic and assumes a Finnhub-like JSON shape.
    It is primarily used as a fallback when broker-grade data is unavailable.
    """

    provider_name = "free"

    def __init__(self) -> None:
        self._base_url = FREE_MARKET_BASE_URL

    async def get_quote(self, symbol: str) -> Quote:
        if not (FREE_MARKET_API_KEY and self._base_url):
            raise RuntimeError("Free market API not configured")
        url = f"{self._base_url}/quote"
        params = {"symbol": symbol.upper(), "token": FREE_MARKET_API_KEY}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json() or {}
        price = data.get("c") or data.get("price") or 0
        ts_raw = data.get("t") or data.get("timestamp")
        as_of = _parse_ts(ts_raw)
        now = datetime.now(timezone.utc)
        stale_seconds = int(max(0, (now - as_of).total_seconds()))
        return Quote(
            symbol=symbol.upper(),
            price=price,
            currency="USD",
            as_of=as_of,
            provider=self.provider_name,
            stale_seconds=stale_seconds,
        )

    async def get_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[Bar]:
        # Many free providers have limited intraday history; keep implementation simple.
        if not (FREE_MARKET_API_KEY and self._base_url):
            raise RuntimeError("Free market API not configured")
        url = f"{self._base_url}/stock/candle"
        params = {
            "symbol": symbol.upper(),
            "resolution": _map_interval(interval),
            "from": int(start.astimezone(timezone.utc).timestamp()),
            "to": int(end.astimezone(timezone.utc).timestamp()),
            "token": FREE_MARKET_API_KEY,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json() or {}
        if data.get("s") != "ok":
            return []
        ts = data.get("t") or []
        opens = data.get("o") or []
        highs = data.get("h") or []
        lows = data.get("l") or []
        closes = data.get("c") or []
        vols = data.get("v") or []
        bars: List[Bar] = []
        for idx, ts_val in enumerate(ts):
            period_start = _parse_ts(ts_val)
            bars.append(
                Bar(
                    symbol=symbol.upper(),
                    interval=interval,
                    period_start=period_start,
                    open=_seq_get(opens, idx),
                    high=_seq_get(highs, idx),
                    low=_seq_get(lows, idx),
                    close=_seq_get(closes, idx),
                    volume=_seq_get(vols, idx, default=0),
                    provider=self.provider_name,
                )
            )
        return bars

    async def search_symbol(self, query: str) -> list[dict]:
        # Optional; implementation can be added when a specific provider is chosen.
        return []

    async def status(self) -> ProviderStatus:
        status = "healthy" if (FREE_MARKET_API_KEY and self._base_url) else "down"
        return ProviderStatus(provider=self.provider_name, status=status)


def _parse_ts(value) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _map_interval(interval: str) -> str:
    """Map generic interval strings to a Finnhub-like resolution."""
    interval = (interval or "").lower()
    if interval in {"1m", "1min"}:
        return "1"
    if interval in {"5m", "5min"}:
        return "5"
    if interval in {"15m", "15min"}:
        return "15"
    if interval in {"30m"}:
        return "30"
    if interval in {"1h", "60m"}:
        return "60"
    if interval in {"1d", "day", "daily"}:
        return "D"
    return "D"


def _seq_get(seq, idx, default=0):
    try:
        return seq[idx]
    except Exception:
        return default

