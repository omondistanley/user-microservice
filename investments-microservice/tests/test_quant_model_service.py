import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.quant_model_service import (
    QuantModelArtifact,
    score_with_artifact,
    train_quant_ranker,
)


def test_train_quant_ranker_produces_backtest_metrics():
    rows = []
    for i in range(40):
        rows.append(
            {
                "heuristic_score": 0.2 + (i % 10) * 0.05,
                "weight": 0.02 * (i % 8),
                "vol_annual": 0.12 + (i % 5) * 0.01,
                "hhi": 0.10 + (i % 6) * 0.02,
                "tlh_loss_scaled": (i % 7) / 10.0,
            }
        )
    artifact = train_quant_ranker(rows, "quant-ranker-v1")
    assert artifact.model_version == "quant-ranker-v1"
    assert artifact.backtest["samples"] == 40
    assert "r2" in artifact.backtest
    assert len(artifact.coef) == len(artifact.feature_names)


def test_score_with_artifact_returns_contributions():
    artifact = QuantModelArtifact(
        model_version="v1",
        feature_names=["heuristic_score", "weight", "vol_annual", "hhi", "tlh_loss_scaled"],
        coef=[0.2, -0.1, -0.05, -0.03, 0.08],
        intercept=0.4,
        means=[0, 0, 0, 0, 0],
        stds=[1, 1, 1, 1, 1],
        backtest={},
    )
    out = score_with_artifact(
        artifact,
        {
            "heuristic_score": 0.7,
            "weight": 0.1,
            "vol_annual": 0.2,
            "hhi": 0.15,
            "tlh_loss_scaled": 0.2,
        },
    )
    assert "factor_contributions" in out
    assert "uncertainty_bucket" in out
    assert 0.0 <= out["model_score"] <= 1.0
