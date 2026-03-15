"""Finnhub market data adapter. Implements MarketDataAdapter for Finnhub API."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

import httpx

from app.core.config import FINNHUB_API_KEY, FINNHUB_BASE_URL
from app.services.market_data_adapter import MarketDataAdapter
from app.services.market_data_models import Bar, ProviderStatus, Quote


def _parse_ts(value) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _map_interval(interval: str) -> str:
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


def _seq_get(seq: list, idx: int, default: float = 0) -> float:
    try:
        return seq[idx]
    except (IndexError, TypeError):
        return default


class FinnhubAdapter(MarketDataAdapter):
    """Finnhub API adapter. Uses /quote and /stock/candle endpoints."""

    provider_name = "finnhub"

    def __init__(self) -> None:
        self._base_url = (FINNHUB_BASE_URL or "").rstrip("/")

    def _configured(self) -> bool:
        return bool(FINNHUB_API_KEY and self._base_url)

    async def get_quote(self, symbol: str) -> Quote:
        if not self._configured():
            raise RuntimeError("Finnhub API not configured")
        url = f"{self._base_url}/quote"
        params = {"symbol": symbol.upper(), "token": FINNHUB_API_KEY}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json() or {}
        price = data.get("c") or data.get("pc") or 0
        ts_raw = data.get("t") or data.get("timestamp")
        as_of = _parse_ts(ts_raw)
        now = datetime.now(timezone.utc)
        stale_seconds = int(max(0, (now - as_of).total_seconds()))
        change_pct = None
        if "dp" in data and data["dp"] is not None:
            try:
                change_pct = Decimal(str(data["dp"]))
            except Exception:
                pass
        return Quote(
            symbol=symbol.upper(),
            price=Decimal(str(price)),
            currency="USD",
            as_of=as_of,
            provider=self.provider_name,
            stale_seconds=stale_seconds,
            change_pct=change_pct,
        )

    async def get_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[Bar]:
        if not self._configured():
            raise RuntimeError("Finnhub API not configured")
        url = f"{self._base_url}/stock/candle"
        params = {
            "symbol": symbol.upper(),
            "resolution": _map_interval(interval),
            "from": int(start.astimezone(timezone.utc).timestamp()),
            "to": int(end.astimezone(timezone.utc).timestamp()),
            "token": FINNHUB_API_KEY,
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
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
                    open=Decimal(str(_seq_get(opens, idx))),
                    high=Decimal(str(_seq_get(highs, idx))),
                    low=Decimal(str(_seq_get(lows, idx))),
                    close=Decimal(str(_seq_get(closes, idx))),
                    volume=Decimal(str(_seq_get(vols, idx, 0))),
                    provider=self.provider_name,
                )
            )
        return bars

    async def search_symbol(self, query: str) -> list[dict]:
        return []

    async def status(self) -> ProviderStatus:
        status = "healthy" if self._configured() else "down"
        return ProviderStatus(provider=self.provider_name, status=status)
