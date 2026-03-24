from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class RecommendationFeatureRow:
    """
    Deterministic feature contract shared between offline training and online inference.
    """

    symbol: str
    heuristic_score: float
    weight: float
    vol_annual: float
    hhi: float
    tlh_loss_scaled: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_feature_row(
    symbol: str,
    heuristic_score: float,
    weight: float,
    vol_annual: float,
    hhi: float,
    tlh_loss_scaled: float,
) -> RecommendationFeatureRow:
    return RecommendationFeatureRow(
        symbol=(symbol or "").strip().upper(),
        heuristic_score=float(heuristic_score),
        weight=float(weight),
        vol_annual=float(vol_annual),
        hhi=float(hhi),
        tlh_loss_scaled=float(tlh_loss_scaled),
    )
