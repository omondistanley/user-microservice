import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.recommendation_quality_service import build_quality_scorecard


class FakeRecSvc:
    def list_recent_runs_for_user(self, user_id: int, limit: int = 5):
        return [
            {"run_id": str(uuid4())},
            {"run_id": str(uuid4())},
        ]

    def list_items_for_run(self, run_id):
        return [
            {"symbol": "AAPL", "score": "0.82", "confidence": "0.74"},
            {"symbol": "MSFT", "score": "0.71", "confidence": "0.66"},
            {"symbol": "VOO", "score": "0.64", "confidence": "0.70"},
        ]


def test_quality_scorecard_shape():
    out = build_quality_scorecard(FakeRecSvc(), user_id=1, runs_limit=5)
    assert out["runs_evaluated"] >= 2
    scorecard = out["scorecard"]
    assert "actionability_rate" in scorecard
    assert "stability_rate" in scorecard
    assert "calibration_gap" in scorecard
    assert "meets_thresholds" in scorecard
