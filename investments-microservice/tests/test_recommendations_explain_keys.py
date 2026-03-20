import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.recommendations as rec_router  # type: ignore  # noqa: E402


@pytest.mark.asyncio
async def test_enrich_explanation_best_effort_keys_exist_on_fail(monkeypatch):
    """When enrichment providers fail, the explain payload should still contain expected keys."""

    # Force all enrich sub-domains to fail.
    market_router = MagicMock()
    market_router.get_quote_with_meta = AsyncMock(side_effect=Exception("quote fail"))
    market_router.get_bars = AsyncMock(side_effect=Exception("bars fail"))

    monkeypatch.setattr(rec_router, "get_news_for_symbol", MagicMock(side_effect=Exception("news fail")))
    monkeypatch.setattr(
        rec_router,
        "get_sentiment_trend_and_summary",
        MagicMock(side_effect=Exception("sentiment fail")),
    )
    monkeypatch.setattr(rec_router, "_db_context", MagicMock(return_value=None))

    expl = {}
    end_dt = datetime.now(timezone.utc)
    start_30d = end_dt - timedelta(days=30)
    start_1y = end_dt - timedelta(days=365)

    await rec_router._enrich_explanation_for_symbol(
        expl=expl,
        enrich_sym="AAPL",
        market_router=market_router,
        end_dt=end_dt,
        start_30d=start_30d,
        start_1y=start_1y,
    )

    assert "data_freshness" in expl
    assert "market" in expl
    assert "enrichment" in expl
    assert "news_factors" in expl
    assert isinstance(expl["news_factors"].get("recent_news"), list)
    assert "news_provider_status" in expl
    assert "sentiment_trend_7d" in expl
    assert isinstance(expl["sentiment_trend_7d"].get("daily_scores"), list)

