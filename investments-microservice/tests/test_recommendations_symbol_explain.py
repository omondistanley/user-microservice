from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.recommendations as rec_router  # type: ignore  # noqa: E402


@pytest.mark.asyncio
async def test_symbol_explain_returns_delta_and_uncertainty(monkeypatch):
    run_id = str(uuid4())
    prev_run_id = str(uuid4())
    user_id = 9
    req = MagicMock()
    req.headers = {}
    req.state = MagicMock()

    rec_svc = MagicMock()
    rec_svc.get_run_for_user.return_value = {"run_id": run_id, "user_id": user_id}
    rec_svc.get_item_for_run_symbol.side_effect = [
        {"symbol": "AAPL", "score": "0.80", "confidence": "0.72", "explanation_json": {"security": {"full_name": "Apple"}}},
        {"symbol": "AAPL", "score": "0.65", "confidence": "0.62", "explanation_json": {"security": {"full_name": "Apple"}}},
    ]
    rec_svc.get_previous_run_for_user.return_value = {"run_id": prev_run_id}

    risk_svc = MagicMock()
    risk_svc.get_risk_profile.return_value = {}
    market_router = MagicMock()
    market_router.get_quote_with_meta = AsyncMock(side_effect=Exception("skip quote"))
    market_router.get_bars = AsyncMock(side_effect=Exception("skip bars"))
    monkeypatch.setattr(rec_router, "get_news_for_symbol", MagicMock(return_value=[]))
    monkeypatch.setattr(rec_router, "get_sentiment_trend_and_summary", MagicMock(return_value=([], None, "")))

    out = await rec_router.explain_recommendation_symbol(
        request=req,
        run_id=run_id,
        symbol="aapl",
        user_id=user_id,
        rec_svc=rec_svc,
        risk_svc=risk_svc,
        market_router=market_router,
    )
    assert out["symbol"] == "AAPL"
    assert "explanation" in out
    assert out["explanation"]["score_delta_vs_prior_run"] == pytest.approx(0.15, abs=1e-6)
    assert out["explanation"]["uncertainty_bucket"] in ("low", "medium", "high")
