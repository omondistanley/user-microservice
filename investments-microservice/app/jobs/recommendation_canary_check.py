"""
Canary comparison utility for legacy vs quant recommendation scores.

This script is intended for rollout checks before enabling quant scoring globally.
"""
from __future__ import annotations

from typing import Dict, List

from app.core.config import RECOMMENDATIONS_QUANT_MODEL_PATH
from app.services.quant_model_service import load_artifact, score_with_artifact


def compare_scores(feature_rows: List[Dict]) -> Dict:
    artifact = load_artifact(RECOMMENDATIONS_QUANT_MODEL_PATH)
    if artifact is None:
        return {"ok": False, "reason": "artifact_missing", "rows": 0}
    deltas = []
    for row in feature_rows:
        legacy = float(row.get("heuristic_score") or 0.0)
        quant = float(score_with_artifact(artifact, row).get("model_score") or 0.0)
        deltas.append(abs(quant - legacy))
    avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
    return {
        "ok": True,
        "rows": len(feature_rows),
        "avg_abs_delta": round(avg_delta, 6),
        "max_abs_delta": round(max(deltas) if deltas else 0.0, 6),
        "threshold_ok": avg_delta <= 0.35,
    }


if __name__ == "__main__":
    sample = [
        {"heuristic_score": 0.62, "weight": 0.10, "vol_annual": 0.16, "hhi": 0.21, "tlh_loss_scaled": 0.0},
        {"heuristic_score": 0.41, "weight": 0.23, "vol_annual": 0.19, "hhi": 0.28, "tlh_loss_scaled": 0.2},
    ]
    print(compare_scores(sample))
