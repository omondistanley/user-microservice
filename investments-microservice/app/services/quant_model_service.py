import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.linear_model import Ridge


FEATURE_NAMES = [
    "heuristic_score",
    "weight",
    "vol_annual",
    "hhi",
    "tlh_loss_scaled",
]


@dataclass
class QuantModelArtifact:
    model_version: str
    feature_names: List[str]
    coef: List[float]
    intercept: float
    means: List[float]
    stds: List[float]
    backtest: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_version": self.model_version,
            "feature_names": self.feature_names,
            "coef": self.coef,
            "intercept": self.intercept,
            "means": self.means,
            "stds": self.stds,
            "backtest": self.backtest,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "QuantModelArtifact":
        return cls(
            model_version=str(payload.get("model_version") or "quant-ranker-v1"),
            feature_names=list(payload.get("feature_names") or FEATURE_NAMES),
            coef=[float(x) for x in (payload.get("coef") or [0.0] * len(FEATURE_NAMES))],
            intercept=float(payload.get("intercept") or 0.0),
            means=[float(x) for x in (payload.get("means") or [0.0] * len(FEATURE_NAMES))],
            stds=[float(x) if float(x) != 0 else 1.0 for x in (payload.get("stds") or [1.0] * len(FEATURE_NAMES))],
            backtest=dict(payload.get("backtest") or {}),
        )


def _build_feature_matrix(rows: List[Dict[str, Any]]) -> np.ndarray:
    data = []
    for row in rows:
        data.append([float(row.get(name) or 0.0) for name in FEATURE_NAMES])
    if not data:
        return np.zeros((0, len(FEATURE_NAMES)), dtype=np.float32)
    return np.array(data, dtype=np.float32)


def _build_target(rows: List[Dict[str, Any]]) -> np.ndarray:
    """
    Pseudo-target used for offline supervised fit when explicit labels are unavailable.
    """
    y = []
    for row in rows:
        h = float(row.get("heuristic_score") or 0.0)
        tlh = float(row.get("tlh_loss_scaled") or 0.0)
        w = float(row.get("weight") or 0.0)
        div_factor = max(0.0, 1.0 - max(0.0, w - 0.10))
        y_val = max(0.0, min(1.0, h * div_factor * (1.0 + 0.10 * tlh)))
        y.append(y_val)
    return np.array(y, dtype=np.float32)


def train_quant_ranker(rows: List[Dict[str, Any]], model_version: str) -> QuantModelArtifact:
    x = _build_feature_matrix(rows)
    y = _build_target(rows)
    if len(x) < 5:
        # Return neutral artifact when sample is too small.
        return QuantModelArtifact(
            model_version=model_version,
            feature_names=FEATURE_NAMES[:],
            coef=[0.0] * len(FEATURE_NAMES),
            intercept=0.0,
            means=[0.0] * len(FEATURE_NAMES),
            stds=[1.0] * len(FEATURE_NAMES),
            backtest={
                "samples": int(len(x)),
                "validation_mode": "not_enough_samples",
                "r2_in_sample_training_set": 0.0,
                "mae_in_sample_training_set": 0.0,
                "turnover_proxy": 0.0,
            },
        )
    means = x.mean(axis=0)
    stds = x.std(axis=0)
    stds = np.where(stds == 0, 1.0, stds)
    xz = (x - means) / stds
    model = Ridge(alpha=1.0, random_state=42)
    model.fit(xz, y)
    preds = np.clip(model.predict(xz), 0.0, 1.0)
    mae = float(np.mean(np.abs(preds - y)))
    r2 = float(model.score(xz, y))
    # Turnover proxy: average rank movement in consecutive 20-row windows.
    turnover_proxy = 0.0
    if len(preds) >= 40:
        moves: List[float] = []
        step = 20
        for i in range(step, len(preds), step):
            prev = np.argsort(-preds[i - step:i])
            cur = np.argsort(-preds[i:min(i + step, len(preds))])
            n = min(len(prev), len(cur))
            if n:
                move = np.mean(np.abs(prev[:n] - cur[:n])) / float(n)
                moves.append(float(move))
        turnover_proxy = float(np.mean(moves)) if moves else 0.0
    return QuantModelArtifact(
        model_version=model_version,
        feature_names=FEATURE_NAMES[:],
        coef=[float(x) for x in model.coef_.tolist()],
        intercept=float(model.intercept_),
        means=[float(x) for x in means.tolist()],
        stds=[float(x) for x in stds.tolist()],
        backtest={
            "samples": int(len(x)),
            "validation_mode": "in_sample_training_set",
            "label_type": "synthetic_heuristic_distillation",
            "r2_in_sample_training_set": round(r2, 4),
            "mae_in_sample_training_set": round(mae, 4),
            "turnover_proxy": round(turnover_proxy, 4),
        },
    )


def load_artifact(path: str) -> Optional[QuantModelArtifact]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return QuantModelArtifact.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None


def save_artifact(path: str, artifact: QuantModelArtifact) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")


def score_with_artifact(artifact: QuantModelArtifact, feature_row: Dict[str, Any]) -> Dict[str, Any]:
    vals = np.array([float(feature_row.get(name) or 0.0) for name in artifact.feature_names], dtype=np.float32)
    means = np.array(artifact.means, dtype=np.float32)
    stds = np.array(artifact.stds, dtype=np.float32)
    stds = np.where(stds == 0, 1.0, stds)
    z = (vals - means) / stds
    raw = float(np.dot(np.array(artifact.coef, dtype=np.float32), z) + artifact.intercept)
    pred = max(0.0, min(1.0, raw))
    contributions: Dict[str, float] = {}
    for i, name in enumerate(artifact.feature_names):
        contributions[name] = round(float(artifact.coef[i] * z[i]), 6)
    uncertainty = "low" if pred >= 0.7 else ("medium" if pred >= 0.4 else "high")
    return {
        "model_score": pred,
        "raw_score": raw,
        "factor_contributions": contributions,
        "uncertainty_bucket": uncertainty,
        "model_version": artifact.model_version,
    }
