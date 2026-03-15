"""Unit tests for MarketDataRouter: provider order and fallback."""
import sys
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.market_data_models import Quote, Bar, ProviderStatus
from app.services.market_data_router import MarketDataRouter


@pytest.fixture
def failing_adapter():
    a = AsyncMock()
    a.get_quote = AsyncMock(side_effect=RuntimeError("provider down"))
    a.get_bars = AsyncMock(side_effect=RuntimeError("provider down"))
    a.status = AsyncMock(return_value=ProviderStatus(provider="fail", status="down"))
    return a


@pytest.fixture
def working_adapter():
    a = AsyncMock()
    now = datetime.now(timezone.utc)
    a.get_quote = AsyncMock(
        return_value=Quote(
            symbol="AAPL",
            price=Decimal("150.00"),
            currency="USD",
            as_of=now,
            provider="working",
            stale_seconds=0,
        )
    )
    a.get_bars = AsyncMock(
        return_value=[
            Bar(
                symbol="AAPL",
                interval="1d",
                period_start=now,
                open=Decimal("149"),
                high=Decimal("151"),
                low=Decimal("148"),
                close=Decimal("150"),
                volume=Decimal("1000000"),
                provider="working",
            )
        ]
    )
    a.status = AsyncMock(return_value=ProviderStatus(provider="working", status="healthy"))
    return a


@pytest.mark.asyncio
async def test_router_uses_second_provider_when_first_fails(working_adapter, failing_adapter):
    """When first provider in order fails, router returns result from second."""
    router = MarketDataRouter(
        alpaca=failing_adapter,
        free=working_adapter,
        finnhub=None,
        twelvedata=None,
        alphavantage=None,
    )
    router._order = ["alpaca", "free"]
    quote, fallback_used, provenance = await router.get_quote_with_meta("AAPL")
    assert quote.symbol == "AAPL"
    assert quote.provider == "working"
    assert fallback_used is True


@pytest.mark.asyncio
async def test_router_returns_fallback_used_false_when_first_succeeds(working_adapter, failing_adapter):
    router = MarketDataRouter(
        alpaca=working_adapter,
        free=failing_adapter,
        finnhub=None,
        twelvedata=None,
        alphavantage=None,
    )
    router._order = ["alpaca", "free"]
    quote, fallback_used, provenance = await router.get_quote_with_meta("AAPL")
    assert quote.provider == "working"
    assert fallback_used is False


@pytest.mark.asyncio
async def test_get_provider_statuses_returns_all_configured():
    router = MarketDataRouter()
    statuses = await router.get_provider_statuses()
    assert isinstance(statuses, list)
    names = [s["provider"] for s in statuses]
    assert "alpaca" in names
    assert "finnhub" in names
    assert "twelvedata" in names
    assert "alphavantage" in names
