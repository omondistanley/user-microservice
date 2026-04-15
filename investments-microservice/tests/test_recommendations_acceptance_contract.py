import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.monte_carlo import _run_monte_carlo
from app.routers.recommendations import _build_proposal_block
from app.services.recommendation_engine import _lgbm_rerank


def test_build_proposal_block_has_required_fields():
    proposal = _build_proposal_block("0.72", "0.81", "0.05")
    assert proposal["method"] == "score_weight_heuristic_v1"
    assert proposal["action"] in {
        "review_or_reduce",
        "consider_incremental_increase",
        "consider_trimming",
        "hold_near_target",
    }
    assert isinstance(proposal["current_weight"], float)
    assert isinstance(proposal["target_weight"], float)
    assert isinstance(proposal["delta_from_current"], float)
    assert isinstance(proposal["turnover_estimate"], float)


def test_lgbm_rerank_exposes_fit_summary_even_when_skipped():
    out = _lgbm_rerank(
        heuristic_items=[{"symbol": "AAPL", "heuristic_score": Decimal("0.3"), "weight": Decimal("0.1")}],
        vol_annual=Decimal("0.2"),
        hhi=Decimal("0.2"),
        tlh_symbols={},
    )
    assert "__fit_summary" in out
    fit = out["__fit_summary"]
    assert fit["label_type"] == "synthetic_heuristic_distillation"
    assert fit["status"] in {"skipped", "trained"}


def test_monte_carlo_core_outputs_percentiles():
    out = _run_monte_carlo(
        initial_value=10000,
        monthly_contribution=500,
        years=10,
        return_assumption=0.07,
        volatility=0.15,
        n_paths=200,
        goal_amount=250000,
    )
    for key in ("p5", "p25", "p50", "p75", "p95", "goal_probability", "sample_paths", "paths_count", "months"):
        assert key in out
