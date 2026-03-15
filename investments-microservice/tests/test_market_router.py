from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402
from app.services.market_data_models import Bar, Quote  # noqa: E402
import app.routers.market as market_router  # noqa: E402


client = TestClient(app)


class FakeRouter:
    async def get_quote(self, symbol: str) -> Quote:
        quote, _, _ = await self.get_quote_with_meta(symbol)
        return quote

    async def get_quote_with_meta(self, symbol: str):
        now = datetime.now(timezone.utc)
        quote = Quote(
            symbol=symbol.upper(),
            price="123.45",
            currency="USD",
            as_of=now,
            provider="fake",
            stale_seconds=0,
        )
        return quote, False, None

    async def get_bars(self, symbol: str, interval: str, start: datetime, end: datetime):
        return [
            Bar(
                symbol=symbol.upper(),
                interval=interval,
                period_start=start,
                open="1",
                high="2",
                low="0.5",
                close="1.5",
                volume="10",
                provider="fake",
            )
        ]

    async def get_provider_statuses(self):
        return [{"provider": "fake", "status": "healthy"}]


@pytest.fixture(autouse=True)
def override_router_dependency(monkeypatch):
    monkeypatch.setattr(market_router, "get_default_market_data_router", lambda: FakeRouter())
    yield


def test_get_quote_returns_normalized_payload():
    r = client.get("/api/v1/market/quote/MSFT")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "MSFT"
    assert body["price"] == "123.45"
    assert body["provider"] == "fake"
    assert "fallback_used" in body
    assert body["fallback_used"] is False


def test_get_bars_requires_start_and_end():
    r = client.get("/api/v1/market/bars/MSFT?interval=1d")
    assert r.status_code == 400


def test_get_bars_returns_series():
    start = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    r = client.get(f"/api/v1/market/bars/MSFT", params={"interval": "1d", "start": start, "end": end})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "MSFT"
    assert body["interval"] == "1d"
    assert len(body["items"]) == 1


def test_providers_status_returns_list():
    r = client.get("/api/v1/market/providers/status")
    assert r.status_code == 200
    body = r.json()
    assert "providers" in body
    assert isinstance(body["providers"], list)

