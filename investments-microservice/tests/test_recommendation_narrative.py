"""Test that recommendation engine attaches narrative and narrative_provider when AI explainer returns them."""
import sys
from pathlib import Path
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.recommendation_engine import RecommendationEngine


@pytest.fixture
def mock_holdings():
    return [
        {"symbol": "AAPL", "quantity": 10, "avg_cost": "150.00", "currency": "USD"},
    ]


@pytest.fixture
def mock_snapshot():
    return None


@pytest.fixture
def mock_risk():
    return {"risk_tolerance": "balanced"}


@pytest.fixture
def holdings_svc(mock_holdings):
    s = MagicMock()
    s.list_all_holdings_for_user.return_value = mock_holdings
    return s


@pytest.fixture
def snapshot_svc(mock_snapshot):
    s = MagicMock()
    s.get_latest_snapshot.return_value = mock_snapshot
    return s


@pytest.fixture
def risk_svc(mock_risk):
    s = MagicMock()
    s.get_risk_profile.return_value = mock_risk
    return s


@pytest.fixture
def rec_svc():
    s = MagicMock()
    s.create_run.return_value = {"run_id": "00000000-0000-0000-0000-000000000001"}
    s.insert_items.return_value = None
    return s


def test_engine_attaches_narrative_and_provider_to_explanation(
    holdings_svc, snapshot_svc, risk_svc, rec_svc
):
    """When generate_narrative returns (text, provider), explanation_json gets narrative and narrative_provider."""
    with patch("app.services.recommendation_engine.ai_explainer_enabled", return_value=True):
        with patch(
            "app.services.recommendation_engine.generate_narrative",
            new_callable=AsyncMock,
            return_value=("This position shows moderate risk-adjusted return.", "groq"),
        ):
            engine = RecommendationEngine(
                holdings_svc=holdings_svc,
                snapshot_svc=snapshot_svc,
                risk_svc=risk_svc,
                rec_svc=rec_svc,
            )
            result = engine.run_for_user(1)
    rec_svc.insert_items.assert_called_once()
    call_args = rec_svc.insert_items.call_args
    run_id = call_args[0][0]
    items = call_args[0][1]
    assert run_id == "00000000-0000-0000-0000-000000000001"
    assert len(items) >= 1
    narrative_items = [it for it in items if (it.get("explanation_json") or {}).get("narrative")]
    assert narrative_items, "Expected at least one item to have narrative attached."
    expl = narrative_items[0].get("explanation_json") or {}
    assert expl.get("narrative") == "This position shows moderate risk-adjusted return."
    assert expl.get("narrative_provider") == "groq"
