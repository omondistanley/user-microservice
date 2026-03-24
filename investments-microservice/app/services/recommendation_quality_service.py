from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set

from app.core.config import (
    REC_QUALITY_MIN_ACTIONABILITY,
    REC_QUALITY_MIN_CALIBRATION_GAP,
    REC_QUALITY_MIN_STABILITY,
)
from app.services.recommendation_data_service import RecommendationDataService


@dataclass
class QualityScorecard:
    actionability_rate: float
    stability_rate: float
    calibration_gap: float
    meets_thresholds: Dict[str, bool]
    thresholds: Dict[str, float]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "actionability_rate": round(self.actionability_rate, 4),
            "stability_rate": round(self.stability_rate, 4),
            "calibration_gap": round(self.calibration_gap, 4),
            "meets_thresholds": self.meets_thresholds,
            "thresholds": self.thresholds,
        }


def _set_of_symbols(items: List[Dict[str, Any]], top_n: int = 10) -> Set[str]:
    out: Set[str] = set()
    for it in items[:top_n]:
        s = str(it.get("symbol") or "").strip().upper()
        if s:
            out.add(s)
    return out


def build_quality_scorecard(rec_svc: RecommendationDataService, user_id: int, runs_limit: int = 5) -> Dict[str, Any]:
    runs = rec_svc.list_recent_runs_for_user(user_id, limit=runs_limit)
    if len(runs) < 2:
        scorecard = QualityScorecard(
            actionability_rate=0.0,
            stability_rate=1.0,
            calibration_gap=0.0,
            meets_thresholds={
                "actionability_rate": False,
                "stability_rate": True,
                "calibration_gap": True,
            },
            thresholds={
                "actionability_rate": REC_QUALITY_MIN_ACTIONABILITY,
                "stability_rate": REC_QUALITY_MIN_STABILITY,
                "calibration_gap": REC_QUALITY_MIN_CALIBRATION_GAP,
            },
        )
        return {"runs_evaluated": len(runs), "scorecard": scorecard.as_dict()}

    # Stability: overlap of top-N symbols between adjacent runs.
    overlaps: List[float] = []
    # Calibration proxy: avg confidence minus avg score.
    calibration_gaps: List[float] = []
    actionability_hits = 0
    actionability_total = 0

    prev_items: List[Dict[str, Any]] = []
    for idx, run in enumerate(runs):
        run_items = rec_svc.list_items_for_run(run["run_id"])
        if idx > 0 and prev_items:
            a = _set_of_symbols(prev_items)
            b = _set_of_symbols(run_items)
            denom = max(1, len(a.union(b)))
            overlaps.append(len(a.intersection(b)) / float(denom))
        # actionability proxy: very high score/confidence implies a likely actionable suggestion
        for it in run_items[:10]:
            actionability_total += 1
            score = float(it.get("score") or 0.0)
            conf = float(it.get("confidence") or 0.0)
            if score >= 0.65 and conf >= 0.60:
                actionability_hits += 1
            calibration_gaps.append(abs(conf - score))
        prev_items = run_items

    stability_rate = sum(overlaps) / len(overlaps) if overlaps else 1.0
    actionability_rate = (
        float(actionability_hits) / float(actionability_total) if actionability_total else 0.0
    )
    calibration_gap = (
        float(sum(calibration_gaps)) / float(len(calibration_gaps)) if calibration_gaps else 0.0
    )
    thresholds = {
        "actionability_rate": REC_QUALITY_MIN_ACTIONABILITY,
        "stability_rate": REC_QUALITY_MIN_STABILITY,
        "calibration_gap": REC_QUALITY_MIN_CALIBRATION_GAP,
    }
    scorecard = QualityScorecard(
        actionability_rate=actionability_rate,
        stability_rate=stability_rate,
        calibration_gap=calibration_gap,
        meets_thresholds={
            "actionability_rate": actionability_rate >= thresholds["actionability_rate"],
            "stability_rate": stability_rate >= thresholds["stability_rate"],
            "calibration_gap": calibration_gap <= thresholds["calibration_gap"],
        },
        thresholds=thresholds,
    )
    return {"runs_evaluated": len(runs), "scorecard": scorecard.as_dict()}
