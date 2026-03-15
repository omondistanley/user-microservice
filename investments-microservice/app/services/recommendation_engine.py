from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List
import asyncio
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
from app.services.ai_explainer import generate_narrative, is_enabled as ai_explainer_enabled
from app.services.analyst_universe import get_analyst_universe


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


def _score_universe_candidate(
    candidate: Dict[str, Any],
    risk: Dict[str, Any],
) -> Decimal:
    """
    Score a universe candidate (symbol, sector, risk_band) against user preferences.
    Higher = better fit for making/saving money and avoiding losses given risk_tolerance,
    industry_preferences, sharpe_objective, loss_aversion.
    """
    score = Decimal("1.0")
    risk_tolerance = (risk.get("risk_tolerance") or "balanced").lower()
    industries = risk.get("industry_preferences") or []
    if isinstance(industries, str):
        industries = [s.strip().lower() for s in industries.split(",")] if industries else []
    elif not isinstance(industries, list):
        industries = []
    else:
        industries = [str(x).strip().lower() for x in industries if x]
    loss_aversion = (risk.get("loss_aversion") or "moderate").lower()
    candidate_band = (candidate.get("risk_band") or "balanced").lower()
    candidate_sector = (candidate.get("sector") or "broad_market").lower().replace(" ", "_")

    # Risk band alignment: conservative user prefers conservative symbols, etc.
    band_order = ("conservative", "balanced", "aggressive")
    try:
        user_idx = band_order.index(risk_tolerance)
        cand_idx = band_order.index(candidate_band)
        # Prefer same or adjacent; penalize large gap (e.g. conservative user + aggressive symbol)
        gap = abs(user_idx - cand_idx)
        if gap == 0:
            score += Decimal("0.5")
        elif gap == 1:
            score += Decimal("0.2")
        else:
            score -= Decimal("0.4")
    except ValueError:
        pass

    # Industry/sector match: bonus if user prefers this sector
    if industries and candidate_sector in industries:
        score += Decimal("0.6")
    elif industries and candidate_sector == "broad_market":
        score += Decimal("0.3")
    elif not industries and candidate_sector == "broad_market":
        score += Decimal("0.2")

    # Loss aversion: high loss_aversion -> favor conservative symbols more
    if loss_aversion == "high" and candidate_band == "conservative":
        score += Decimal("0.4")
    elif loss_aversion == "low" and candidate_band == "aggressive":
        score += Decimal("0.2")

    return max(Decimal("0"), score)


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

    def _run_no_holdings(self, user_id: int, risk: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate recommendations when user has no holdings: suggest a starter portfolio
        from the analyst universe, scored by risk_tolerance, industry_preferences,
        sharpe_objective, and loss_aversion. Explanations are analyst-style: aimed at
        helping the user make money, save money, and avoid losses.
        """
        universe = get_analyst_universe()
        scored: List[tuple] = []
        for c in universe:
            sym = (c.get("symbol") or "").strip().upper()
            if not sym:
                continue
            s = _score_universe_candidate(c, risk)
            scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        top_n = 12
        chosen = [item for _, item in scored[:top_n]]

        items_with_scores: List[Dict[str, Any]] = []
        for rank, c in enumerate(chosen, 1):
            sym = (c.get("symbol") or "").strip().upper()
            sector = (c.get("sector") or "broad_market").replace("_", " ").title()
            risk_band = (c.get("risk_band") or "balanced").lower()
            desc = c.get("description") or sym
            # Normalize score to 0–1 range for display; use rank so higher rank = higher score
            combined = Decimal("1") - (Decimal(rank - 1) / Decimal(max(len(chosen), 1))) * Decimal("0.5")
            conf = Decimal("0.85") - (Decimal(rank - 1) / Decimal(max(len(chosen), 1))) * Decimal("0.2")
            conf = max(Decimal("0.5"), min(Decimal("1"), conf))

            why = [
                f"Suggested to build a diversified portfolio aligned with your risk profile ({risk.get('risk_tolerance') or 'balanced'}).",
                f"Sector: {sector}. Fits goal of seeking risk-adjusted return and avoiding unnecessary losses.",
            ]
            if risk.get("industry_preferences"):
                why.append("Matches or complements your stated industry/sector preferences.")
            why.append(f"Use this as a starting idea; add the symbol to Holdings when you are ready.")

            explanation: Dict[str, Any] = {
                "why_selected": why,
                "key_risk_contributors": [
                    f"risk_band={risk_band}",
                    f"sector={sector}",
                    "diversification_builder=True",
                ],
                "risk_metrics": {
                    "sharpe": "N/A (no position yet)",
                    "volatility_annual": "N/A",
                    "max_drawdown": "N/A",
                    "weight": "0",
                },
                "data_freshness": {"provider": "analyst_universe", "stale_seconds": None},
                "confidence": {
                    "value": float(conf),
                    "reason": "Based on your risk tolerance, industry preferences, and loss-aversion profile.",
                },
                "news_factors": {"sentiment_score_7d": None, "event_flags": []},
                "analyst_note": f"{desc}. Suggested to help you build a portfolio that can grow while managing risk.",
            }

            if ai_explainer_enabled():
                try:
                    loop = asyncio.get_event_loop()
                    narrative, narrative_provider = loop.run_until_complete(generate_narrative(explanation))
                    if narrative:
                        explanation["narrative"] = narrative
                        if narrative_provider:
                            explanation["narrative_provider"] = narrative_provider
                except Exception:
                    pass

            items_with_scores.append({
                "symbol": sym,
                "score": combined,
                "confidence": conf,
                "explanation_json": explanation,
            })

        run = self.rec_svc.create_run(
            user_id=user_id,
            model_version="analyst-universe-v1",
            feature_snapshot_id=None,
            training_cutoff_date=date.today() - timedelta(days=1),
            notes="No-holdings starter portfolio suggestions",
        )
        run_id = run.get("run_id")
        if run_id:
            self.rec_svc.insert_items(run_id, items_with_scores)
        zero = Decimal("0")
        return {
            "run": run,
            "items": [
                {"symbol": i["symbol"], "score": str(i["score"]), "confidence": float(i["confidence"])}
                for i in items_with_scores
            ],
            "portfolio": {
                "total_value": str(zero),
                "total_cost_basis": str(zero),
                "unrealized_pl": str(zero),
                "realized_pl": str(zero),
                "sharpe": str(zero),
                "volatility_annual": str(zero),
                "max_drawdown": str(zero),
                "top1_weight": str(zero),
                "top3_weight": str(zero),
                "hhi": str(zero),
            },
        }

    def run_for_user(self, user_id: int) -> Dict[str, Any]:
        """Generate recommendations, persist run + items, and return summary.
        Works with or without holdings: no holdings = suggest starter portfolio from analyst universe
        using industry/risk/Sharpe preferences to help user make money, save money, and avoid losses.
        """
        holdings_rows = self.holdings_svc.list_all_holdings_for_user(user_id)
        risk = self.risk_svc.get_risk_profile(user_id) or {}

        # No-holdings path: suggest a starter portfolio from analyst universe (preference-aware).
        if not holdings_rows:
            return self._run_no_holdings(user_id, risk)

        # With-holdings path: rank existing positions + preference-aware scoring.
        snapshot = self.snapshot_svc.get_latest_snapshot(user_id)
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

            why_selected = [
                "Risk-adjusted score based on portfolio Sharpe ratio and current position weight.",
            ]
            if risk.get("risk_tolerance"):
                why_selected.append(f"Your risk tolerance ({risk.get('risk_tolerance')}) is reflected in the score.")
            if risk.get("sharpe_objective") is not None:
                why_selected.append("Compared against your target Sharpe objective to favor risk-adjusted return.")
            why_selected.append("Aims to support making money and avoiding undue losses via diversification and weight limits.")

            explanation: Dict[str, Any] = {
                "why_selected": why_selected,
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
                    "provider": "unknown",
                    "stale_seconds": None,
                },
                "confidence": {
                    "value": float(conf),
                    "reason": "Based on portfolio volatility and concentration metrics.",
                },
                "news_factors": {
                    "sentiment_score_7d": None,
                    "event_flags": [],
                },
            }

            # Optional AI-generated narrative (tri-provider: groq, brave, generic).
            # Best-effort; on failure run continues without narrative.
            if ai_explainer_enabled():
                try:
                    loop = asyncio.get_event_loop()
                    narrative, narrative_provider = loop.run_until_complete(generate_narrative(explanation))
                    if narrative:
                        explanation["narrative"] = narrative
                        if narrative_provider:
                            explanation["narrative_provider"] = narrative_provider
                except Exception:
                    pass

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

