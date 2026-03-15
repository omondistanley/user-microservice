"""TwelveData market data adapter. Implements MarketDataAdapter for Twelve Data API."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List

import httpx

from app.core.config import TWELVEDATA_API_KEY, TWELVEDATA_BASE_URL
from app.services.market_data_adapter import MarketDataAdapter
from app.services.market_data_models import Bar, ProviderStatus, Quote


def _parse_ts(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    try:
        s = str(value).strip()
        if not s:
            return datetime.now(timezone.utc)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _map_interval(interval: str) -> str:
    interval = (interval or "").lower()
    if interval in {"1m", "1min"}:
        return "1min"
    if interval in {"5m", "5min"}:
        return "5min"
    if interval in {"15m", "15min"}:
        return "15min"
    if interval in {"30m"}:
        return "30min"
    if interval in {"1h", "60m"}:
        return "1h"
    if interval in {"1d", "day", "daily"}:
        return "1day"
    return "1day"


class TwelveDataAdapter(MarketDataAdapter):
    """Twelve Data API adapter. Uses /quote and /time_series endpoints."""

    provider_name = "twelvedata"

    def __init__(self) -> None:
        self._base_url = (TWELVEDATA_BASE_URL or "").rstrip("/")

    def _configured(self) -> bool:
        return bool(TWELVEDATA_API_KEY and self._base_url)

    async def get_quote(self, symbol: str) -> Quote:
        if not self._configured():
            raise RuntimeError("TwelveData API not configured")
        url = f"{self._base_url}/quote"
        params = {"symbol": symbol.upper(), "apikey": TWELVEDATA_API_KEY}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json() or {}
        close = data.get("close") or data.get("previous_close") or 0
        ts_raw = data.get("timestamp") or data.get("datetime")
        as_of = _parse_ts(ts_raw)
        now = datetime.now(timezone.utc)
        stale_seconds = int(max(0, (now - as_of).total_seconds()))
        return Quote(
            symbol=symbol.upper(),
            price=Decimal(str(close)),
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
        if not self._configured():
            raise RuntimeError("TwelveData API not configured")
        url = f"{self._base_url}/time_series"
        params = {
            "symbol": symbol.upper(),
            "interval": _map_interval(interval),
            "apikey": TWELVEDATA_API_KEY,
            "start_date": start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": end.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "outputsize": 5000,
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json() or {}
        values = data.get("values") or []
        bars: List[Bar] = []
        for row in values:
            dt_str = row.get("datetime")
            period_start = _parse_ts(dt_str)
            o = Decimal(str(row.get("open", 0)))
            h = Decimal(str(row.get("high", 0)))
            l = Decimal(str(row.get("low", 0)))
            c = Decimal(str(row.get("close", 0)))
            v = Decimal(str(row.get("volume", 0)))
            bars.append(
                Bar(
                    symbol=symbol.upper(),
                    interval=interval,
                    period_start=period_start,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=v,
                    provider=self.provider_name,
                )
            )
        bars.sort(key=lambda b: b.period_start)
        return bars

    async def search_symbol(self, query: str) -> list[dict]:
        return []

    async def status(self) -> ProviderStatus:
        status = "healthy" if self._configured() else "down"
        return ProviderStatus(provider=self.provider_name, status=status)
