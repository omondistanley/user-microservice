from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.rebalance_planner import DEFAULT_PARAMS, RebalanceChurnParams, RebalancePlanner
from app.services.recommendation_engine import RecommendationEngine


def _utc(dt_days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=dt_days_ago)


def test_confidence_gate_fail_results_no_action():
    planner = RebalancePlanner(DEFAULT_PARAMS)
    holdings = [{"symbol": "AAPL", "quantity": "1", "avg_cost": "150", "holding_id": "h1", "created_at": _utc(30)}]
    # AAPL is held, so only new_top_buy candidates exist for other symbols; set low confidence.
    items_ranked = [
        {"symbol": "AAPL", "score": "0.2", "confidence": 0.9},
        {"symbol": "MSFT", "score": "0.8", "confidence": 0.50},
        {"symbol": "QQQ", "score": "0.7", "confidence": 0.40},
    ]
    out = planner.plan(
        now_utc=_utc(0),
        trigger_type="auto_4w",
        holdings_rows=holdings,
        items_ranked=items_ranked,
        prev_session_payload=None,
        last_sell_completed_at=_utc(10),
        force_scenario1=False,
        target_scenario=None,
        finance_ctx=None,
    )
    assert out["scenario"] == "no_action"
    assert not out["sell_orders"]
    assert not out["buy_orders"]


def test_force_scenario1_bypasses_material_change_gate():
    planner = RebalancePlanner(DEFAULT_PARAMS)
    holdings = [{"symbol": "AAPL", "quantity": "1", "avg_cost": "150", "holding_id": "h1", "created_at": _utc(30)}]

    # new_top_buy_symbols should equal prev_top_buy_symbols so material_change_strength is ~0.
    items_ranked = [
        {"symbol": "AAPL", "score": "0.2", "confidence": 0.9},
        {"symbol": "MSFT", "score": "0.9", "confidence": float(DEFAULT_PARAMS.confidence_min) + 0.1},
        {"symbol": "QQQ", "score": "0.8", "confidence": float(DEFAULT_PARAMS.confidence_min) + 0.1},
    ]

    prev_payload = {
        "top_buy_symbols": ["MSFT", "QQQ"],
        "top_buy_scores": {"MSFT": "0.9", "QQQ": "0.8"},
    }

    out = planner.plan(
        now_utc=_utc(0),
        trigger_type="manual",
        holdings_rows=holdings,
        items_ranked=items_ranked,
        prev_session_payload=prev_payload,
        last_sell_completed_at=_utc(10),
        force_scenario1=True,
        target_scenario=None,
        finance_ctx=None,
    )

    assert out["scenario"] == "scenario1"


def test_target_scenario_bypasses_material_gate_on_buy_phase():
    planner = RebalancePlanner(DEFAULT_PARAMS)
    holdings = [{"symbol": "AAPL", "quantity": "1", "avg_cost": "150", "holding_id": "h1", "created_at": _utc(30)}]
    items_ranked = [
        {"symbol": "AAPL", "score": "0.2", "confidence": 0.9},
        {"symbol": "MSFT", "score": "0.9", "confidence": float(DEFAULT_PARAMS.confidence_min) + 0.1},
    ]
    prev_payload = {"top_buy_symbols": ["MSFT"], "top_buy_scores": {"MSFT": "0.9"}}
    out = planner.plan(
        now_utc=_utc(0),
        trigger_type="auto_4w:buy_next_day",
        holdings_rows=holdings,
        items_ranked=items_ranked,
        prev_session_payload=prev_payload,
        last_sell_completed_at=_utc(0),
        force_scenario1=False,
        target_scenario="scenario2",
        finance_ctx=None,
    )
    assert out["scenario"] == "scenario2"


def test_hysteresis_and_min_hold_and_sell_cooldown():
    params = DEFAULT_PARAMS
    planner = RebalancePlanner(params)

    # Three holdings; only ranks > N_KEEP should become sell-eligible.
    # Use created_at older than min_hold_days for all.
    holdings = [
        {"symbol": "H1", "quantity": "1", "avg_cost": "10", "holding_id": "h1", "created_at": _utc(params.min_hold_days + 2)},
        {"symbol": "H2", "quantity": "1", "avg_cost": "10", "holding_id": "h2", "created_at": _utc(params.min_hold_days + 2)},
        {"symbol": "H3", "quantity": "1", "avg_cost": "10", "holding_id": "h3", "created_at": _utc(params.min_hold_days + 2)},
    ]

    # Arrange ranks so H1 is within N_KEEP and H2/H3 are outside it.
    items_ranked = [{"symbol": "X", "score": "0.1", "confidence": 0.9}]  # rank 1
    for i in range(1, params.n_keep + 1):  # ranks 2..n_keep+1
        items_ranked.append({"symbol": f"KEEP{i}", "score": str(0.1 + i * 0.01), "confidence": 0.9})
    # Now ranks: ensure H1 is inside keep band: rank 3 (we'll place it where rank <= N_KEEP)
    # and H2/H3 outside: rank > N_KEEP.
    items_ranked.insert(1, {"symbol": "H1", "score": "0.5", "confidence": 0.9})  # shift ranks deterministically
    items_ranked.append({"symbol": "H2", "score": "0.2", "confidence": 0.9})
    items_ranked.append({"symbol": "H3", "score": "0.2", "confidence": 0.9})
    items_ranked.append({"symbol": "BUY1", "score": "1.0", "confidence": float(params.confidence_min) + 0.2})

    # Sell cooldown satisfied.
    out_ok = planner.plan(
        now_utc=_utc(0),
        trigger_type="auto_4w",
        holdings_rows=holdings,
        items_ranked=items_ranked,
        prev_session_payload=None,
        last_sell_completed_at=_utc(params.sell_cooldown_days + 10),
        force_scenario1=False,
        target_scenario=None,
        finance_ctx=None,
    )
    assert out_ok["sell_orders"], "Expected sells when hysteresis + cooldown are satisfied"
    sell_syms_ok = {s["symbol"] for s in out_ok["sell_orders"]}
    assert "H2" in sell_syms_ok
    assert "H3" in sell_syms_ok
    assert "H1" not in sell_syms_ok

    # Sell cooldown blocked.
    out_blocked = planner.plan(
        now_utc=_utc(0),
        trigger_type="auto_4w",
        holdings_rows=holdings,
        items_ranked=items_ranked,
        prev_session_payload=None,
        last_sell_completed_at=_utc(1),
        force_scenario1=False,
        target_scenario=None,
        finance_ctx=None,
    )
    assert not out_blocked["sell_orders"]


def test_position_change_caps():
    # Ensure max_sells_per_rebalance and max_position_changes_per_rebalance cap sells/buys.
    caps = RebalanceChurnParams(
        min_hold_days=1,
        confidence_min=Decimal("0.62"),
        delta_strength_min=Decimal("0.00"),  # always material enough
        n_keep=1,
        n_buy=5,
        max_sells_per_rebalance=2,
        max_position_changes_per_rebalance=3,  # max total (sells + buys)
        sell_cooldown_days=0,
        market_confidence_threshold=Decimal("0.75"),
    )
    planner = RebalancePlanner(caps)

    holdings = [
        {"symbol": "S1", "quantity": "1", "avg_cost": "10", "holding_id": "h1", "created_at": _utc(10)},
        {"symbol": "S2", "quantity": "1", "avg_cost": "10", "holding_id": "h2", "created_at": _utc(10)},
        {"symbol": "S3", "quantity": "1", "avg_cost": "10", "holding_id": "h3", "created_at": _utc(10)},
    ]

    # Ranks: only S1 inside N_KEEP=1, others outside.
    items_ranked = [
        {"symbol": "S1", "score": "0.1", "confidence": 0.9},
        {"symbol": "S2", "score": "0.2", "confidence": 0.9},
        {"symbol": "S3", "score": "0.3", "confidence": 0.9},
        {"symbol": "B1", "score": "1.0", "confidence": 0.9},
        {"symbol": "B2", "score": "0.9", "confidence": 0.9},
        {"symbol": "B3", "score": "0.8", "confidence": 0.9},
        {"symbol": "B4", "score": "0.7", "confidence": 0.9},
    ]

    out = planner.plan(
        now_utc=_utc(0),
        trigger_type="auto_4w",
        holdings_rows=holdings,
        items_ranked=items_ranked,
        prev_session_payload=None,
        last_sell_completed_at=_utc(100),
        force_scenario1=False,
        target_scenario=None,
        finance_ctx=None,
    )
    assert len(out["sell_orders"]) <= 2
    assert len(out["sell_orders"]) + len(out["buy_orders"]) <= 3


def test_engine_does_not_call_ai_when_include_ai_narratives_false():
    mock_holdings = [{"symbol": "AAPL", "quantity": 10, "avg_cost": "150.00", "currency": "USD"}]

    holdings_svc = MagicMock()
    holdings_svc.list_all_holdings_for_user.return_value = mock_holdings

    snapshot_svc = MagicMock()
    snapshot_svc.get_latest_snapshot.return_value = None

    risk_svc = MagicMock()
    risk_svc.get_risk_profile.return_value = {"risk_tolerance": "balanced", "use_finance_data_for_recommendations": False}

    rec_svc = MagicMock()
    rec_svc.create_run.return_value = {"run_id": "00000000-0000-0000-0000-000000000001"}
    rec_svc.insert_items.return_value = None
    rec_svc.update_run_portfolio_snapshot.return_value = None

    engine = RecommendationEngine(
        holdings_svc=holdings_svc,
        snapshot_svc=snapshot_svc,
        risk_svc=risk_svc,
        rec_svc=rec_svc,
    )

    with patch("app.services.recommendation_engine.ai_explainer_enabled", return_value=True):
        with patch("app.services.recommendation_engine.generate_narrative", new_callable=AsyncMock) as m_gen:
            m_gen.return_value = ("SHOULD_NOT_BE_CALLED", "groq")
            engine.run_for_user(1, include_ai_narratives=False)

    assert m_gen.call_count == 0

