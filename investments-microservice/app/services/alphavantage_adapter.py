"""Alpha Vantage market data adapter. Implements MarketDataAdapter for Alpha Vantage API."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import ALPHAVANTAGE_API_KEY, ALPHAVANTAGE_BASE_URL
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
        if " " in s:
            dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


class AlphaVantageAdapter(MarketDataAdapter):
    """Alpha Vantage API adapter. Uses GLOBAL_QUOTE and TIME_SERIES_DAILY."""

    provider_name = "alphavantage"

    def __init__(self) -> None:
        self._base_url = (ALPHAVANTAGE_BASE_URL or "").rstrip("/")

    def _configured(self) -> bool:
        return bool(ALPHAVANTAGE_API_KEY and self._base_url)

    async def get_quote(self, symbol: str) -> Quote:
        if not self._configured():
            raise RuntimeError("Alpha Vantage API not configured")
        url = self._base_url + "/query"
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol.upper(),
            "apikey": ALPHAVANTAGE_API_KEY,
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json() or {}
        gq = data.get("Global Quote") or {}
        price = gq.get("05. price") or gq.get("08. previous close") or 0
        day_str = gq.get("07. latest trading day") or ""
        as_of = _parse_ts(day_str)
        now = datetime.now(timezone.utc)
        stale_seconds = int(max(0, (now - as_of).total_seconds()))
        return Quote(
            symbol=symbol.upper(),
            price=Decimal(str(price)),
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
            raise RuntimeError("Alpha Vantage API not configured")
        url = self._base_url + "/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol.upper(),
            "apikey": ALPHAVANTAGE_API_KEY,
            "outputsize": "full",
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json() or {}
        series = data.get("Time Series (Daily)") or data.get("Time Series (Intraday)") or {}
        bars: List[Bar] = []
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        for date_str, row in series.items():
            if not isinstance(row, dict):
                continue
            period_start = _parse_ts(date_str)
            if period_start < start_utc or period_start > end_utc:
                continue
            o = Decimal(str(row.get("1. open", row.get("open", 0))))
            h = Decimal(str(row.get("2. high", row.get("high", 0))))
            l = Decimal(str(row.get("3. low", row.get("low", 0))))
            c = Decimal(str(row.get("4. close", row.get("close", 0))))
            v = Decimal(str(row.get("5. volume", row.get("volume", 0))))
            bars.append(
                Bar(
                    symbol=symbol.upper(),
                    interval=interval if interval else "1d",
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

    async def get_company_overview(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch company overview (Sector, Industry, Description, Name, AssetType) for symbol."""
        if not self._configured():
            return None
        url = self._base_url + "/query"
        params = {
            "function": "OVERVIEW",
            "symbol": symbol.upper(),
            "apikey": ALPHAVANTAGE_API_KEY,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and (data.get("Name") or data.get("Symbol")):
                return data
            return None
        except Exception:
            return None

    async def status(self) -> ProviderStatus:
        status = "healthy" if self._configured() else "down"
        return ProviderStatus(provider=self.provider_name, status=status)
