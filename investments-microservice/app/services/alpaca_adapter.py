from datetime import datetime, timezone
from typing import List

import httpx

from app.core.config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_DATA_BASE_URL
from .market_data_adapter import MarketDataAdapter
from .market_data_models import Bar, ProviderStatus, Quote


class AlpacaAdapter(MarketDataAdapter):
    provider_name = "alpaca"

    def __init__(self) -> None:
        self._base_url = ALPACA_DATA_BASE_URL

    async def get_quote(self, symbol: str) -> Quote:
        if not (ALPACA_API_KEY and ALPACA_API_SECRET):
            raise RuntimeError("Alpaca API not configured")
        url = f"{self._base_url}/v2/stocks/{symbol.upper()}/quotes/latest"
        headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json() or {}
        quote = data.get("quote") or data
        price = quote.get("ap", quote.get("bp", quote.get("last", 0)))
        ts_raw = quote.get("t") or quote.get("timestamp")
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
        if not (ALPACA_API_KEY and ALPACA_API_SECRET):
            raise RuntimeError("Alpaca API not configured")
        tf = _map_interval(interval)
        url = f"{self._base_url}/v2/stocks/{symbol.upper()}/bars"
        headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
        }
        params = {
            "timeframe": tf,
            "start": start.astimezone(timezone.utc).isoformat(),
            "end": end.astimezone(timezone.utc).isoformat(),
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json() or {}
        items = data.get("bars") or data.get("barset") or []
        bars: List[Bar] = []
        for row in items:
            ts_raw = row.get("t") or row.get("timestamp")
            period_start = _parse_ts(ts_raw)
            bars.append(
                Bar(
                    symbol=symbol.upper(),
                    interval=interval,
                    period_start=period_start,
                    open=row.get("o"),
                    high=row.get("h"),
                    low=row.get("l"),
                    close=row.get("c"),
                    volume=row.get("v", 0),
                    provider=self.provider_name,
                )
            )
        return bars

    async def search_symbol(self, query: str) -> list[dict]:
        # Alpaca does not provide rich search in all plans; keep minimal.
        return []

    async def status(self) -> ProviderStatus:
        # Very lightweight health check: if keys are present, mark as healthy.
        status = "healthy" if (ALPACA_API_KEY and ALPACA_API_SECRET) else "down"
        return ProviderStatus(provider=self.provider_name, status=status)


def _parse_ts(value) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        # assume epoch seconds
        return datetime.fromtimestamp(value, tz=timezone.utc)
    # assume isoformat
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _map_interval(interval: str) -> str:
    """Map generic interval strings to Alpaca timeframes."""
    interval = (interval or "").lower()
    if interval in {"1m", "1min"}:
        return "1Min"
    if interval in {"5m", "5min"}:
        return "5Min"
    if interval in {"15m", "15min"}:
        return "15Min"
    if interval in {"1h", "60m"}:
        return "1Hour"
    if interval in {"1d", "day", "daily"}:
        return "1Day"
    return "1Day"

