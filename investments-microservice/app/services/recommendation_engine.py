from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List
import logging

from app.core.config import RISK_FREE_RATE_ANNUAL
from app.services.analytics_math import (
    concentration_metrics,
    compute_returns,
    max_drawdown,
    rolling_volatility_annualized,
    sharpe_ratio,
)
from app.services.holdings_data_service import HoldingsDataService
from app.services.portfolio_snapshot_service import PortfolioSnapshotDataService
from app.services.recommendation_data_service import RecommendationDataService
from app.services.risk_profile_service import RiskProfileDataService
from app.services.service_factory import ServiceFactory


def _get_holdings_service() -> HoldingsDataService:
    ds = ServiceFactory.get_service("HoldingsDataService")
    assert isinstance(ds, HoldingsDataService)
    return ds


def _get_snapshot_service() -> PortfolioSnapshotDataService:
    ds = ServiceFactory.get_service("PortfolioSnapshotDataService")
    assert isinstance(ds, PortfolioSnapshotDataService)
    return ds


def _get_risk_profile_service() -> RiskProfileDataService:
    ds = ServiceFactory.get_service("RiskProfileDataService")
    assert isinstance(ds, RiskProfileDataService)
    return ds


def _get_recommendation_data_service() -> RecommendationDataService:
    ds = ServiceFactory.get_service("RecommendationDataService")
    assert isinstance(ds, RecommendationDataService)
    return ds


class RecommendationEngine:
    """Two-stage recommendation engine (heuristic + predictive-style reranker).

    For now, the predictive stage is a thin wrapper over heuristic and analytics
    signals, but the structure allows swapping in a real model later.
    """

    def __init__(
        self,
        holdings_svc: HoldingsDataService | None = None,
        snapshot_svc: PortfolioSnapshotDataService | None = None,
        risk_svc: RiskProfileDataService | None = None,
        rec_svc: RecommendationDataService | None = None,
    ) -> None:
        self.holdings_svc = holdings_svc or _get_holdings_service()
        self.snapshot_svc = snapshot_svc or _get_snapshot_service()
        self.risk_svc = risk_svc or _get_risk_profile_service()
        self.rec_svc = rec_svc or _get_recommendation_data_service()
        self.logger = logging.getLogger("investments_recommendations")

    def run_for_user(self, user_id: int) -> Dict[str, Any]:
        """Generate recommendations, persist run + items, and return summary."""
        # Load core inputs
        holdings_rows = self.holdings_svc.list_all_holdings_for_user(user_id)
        snapshot = self.snapshot_svc.get_latest_snapshot(user_id)
        risk = self.risk_svc.get_risk_profile(user_id) or {}

        # Basic portfolio stats from snapshot (or synthetic if missing)
        if snapshot:
            total_value = Decimal(str(snapshot["total_value"]))
            total_cost_basis = Decimal(str(snapshot["total_cost_basis"]))
            unrealized_pl = Decimal(str(snapshot["unrealized_pl"]))
            realized_pl = Decimal(str(snapshot.get("realized_pl") or "0"))
        else:
            total_value = sum(
                Decimal(str(r.get("quantity") or "0")) * Decimal(str(r.get("avg_cost") or "0"))
                for r in holdings_rows
            )
            total_cost_basis = total_value
            unrealized_pl = Decimal("0")
            realized_pl = Decimal("0")

        # Derive weights and concentration metrics
        position_values: List[Decimal] = []
        for r in holdings_rows:
            q = Decimal(str(r.get("quantity") or "0"))
            c = Decimal(str(r.get("avg_cost") or "0"))
            position_values.append(q * c)
        weights: List[Decimal] = []
        if total_value > 0:
            weights = [pv / total_value for pv in position_values]
        top1, top3, hhi = concentration_metrics(weights)

        # For this initial version, approximate portfolio returns via PL changes
        # using a simple two-point series: this is just to feed Sharpe/vol logic.
        # In a real system, we'd use a longer snapshot history.
        portfolio_values = [total_cost_basis, total_value]
        returns = compute_returns(portfolio_values)
        vol_annual = rolling_volatility_annualized(returns)
        mdd = max_drawdown(portfolio_values)
        sharpe = sharpe_ratio(returns, Decimal(str(RISK_FREE_RATE_ANNUAL)))

        # Heuristic scoring per holding (stage 1)
        heuristic_items: List[Dict[str, Any]] = []
        for row, w in zip(holdings_rows, weights or [Decimal("0")] * len(holdings_rows)):
            symbol = str(row.get("symbol") or "").upper()
            # Simple risk-return ratio based on portfolio Sharpe and weight
            risk_tolerance = (risk.get("risk_tolerance") or "balanced").lower()
            base_score = sharpe if sharpe > 0 else Decimal("0")
            # Penalize very large weights
            penalty = Decimal("0")
            if w > Decimal("0.2"):
                penalty += (w - Decimal("0.2")) * Decimal("2")
            if risk_tolerance == "conservative" and vol_annual > (risk.get("target_volatility") or Decimal("0.15")):
                penalty += Decimal("0.5")
            heuristic_score = max(Decimal("0"), base_score - penalty)
            heuristic_items.append(
                {
                    "symbol": symbol,
                    "weight": w,
                    "heuristic_score": heuristic_score,
                }
            )

        # Stage 2: "predictive" reranker (for now, minor non-linear transform)
        items_with_scores: List[Dict[str, Any]] = []
        for item in heuristic_items:
            h_score = Decimal(str(item["heuristic_score"]))
            # Treat this as risk-adjusted performance; compress via logistic-style map
            model_score = h_score / (Decimal("1") + abs(h_score))
            combined = (h_score * Decimal("0.7")) + (model_score * Decimal("0.3"))

            # Confidence index based on volatility and concentration
            # Higher volatility and HHI reduce confidence.
            conf = Decimal("1.0")
            conf -= vol_annual * Decimal("0.5")
            conf -= hhi * Decimal("0.2")
            if conf < Decimal("0"):
                conf = Decimal("0")
            if conf > Decimal("1"):
                conf = Decimal("1")

            explanation = {
                "why_selected": [
                    "Risk-adjusted score based on portfolio Sharpe ratio and current position weight."
                ],
                "key_risk_contributors": [
                    f"portfolio_volatility_annual={str(vol_annual)}",
                    f"portfolio_max_drawdown={str(mdd)}",
                    f"top1_weight={str(top1)}, hhi={str(hhi)}",
                ],
                "risk_metrics": {
                    "sharpe": str(sharpe),
                    "volatility_annual": str(vol_annual),
                    "max_drawdown": str(mdd),
                    "weight": str(item["weight"]),
                },
                "data_freshness": {
                    # Placeholders for now; real implementation would pull from market_quote/provider_health.
                    "provider": "unknown",
                    "stale_seconds": None,
                },
                "confidence": {
                    "value": float(conf),
                    "reason": "Based on portfolio volatility and concentration metrics.",
                },
                "news_factors": {
                    # News integration can populate this later.
                    "sentiment_score_7d": None,
                    "event_flags": [],
                },
            }
            items_with_scores.append(
                {
                    "symbol": item["symbol"],
                    "score": combined,
                    "confidence": conf,
                    "explanation_json": explanation,
                }
            )

        # Persist run + items
        run = self.rec_svc.create_run(
            user_id=user_id,
            model_version="heuristic+analytics-v1",
            feature_snapshot_id=None,
            training_cutoff_date=date.today() - timedelta(days=1),
            notes=None,
        )
        run_id = run.get("run_id")
        if run_id:
            self.rec_svc.insert_items(run_id, items_with_scores)
            # Audit log for governance
            try:
                self.logger.info(
                    "recommendation_run",
                    extra={
                        "user_id": user_id,
                        "run_id": str(run_id),
                        "model_version": "heuristic+analytics-v1",
                        "item_count": len(items_with_scores),
                        "sharpe": str(sharpe),
                        "volatility_annual": str(vol_annual),
                        "max_drawdown": str(mdd),
                    },
                )
            except Exception:
                # Logging should never break recommendation generation
                pass

        return {
            "run": run,
            "items": [
                {
                    "symbol": i["symbol"],
                    "score": str(i["score"]),
                    "confidence": float(i["confidence"]),
                }
                for i in items_with_scores
            ],
            "portfolio": {
                "total_value": str(total_value),
                "total_cost_basis": str(total_cost_basis),
                "unrealized_pl": str(unrealized_pl),
                "realized_pl": str(realized_pl),
                "sharpe": str(sharpe),
                "volatility_annual": str(vol_annual),
                "max_drawdown": str(mdd),
                "top1_weight": str(top1),
                "top3_weight": str(top3),
                "hhi": str(hhi),
            },
        }

