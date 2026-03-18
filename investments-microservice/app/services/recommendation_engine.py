from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import concurrent.futures
import logging

from app.core.config import MAX_RECOMMENDATIONS, RISK_FREE_RATE_ANNUAL
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
from app.services.analyst_universe import get_analyst_universe, get_security_info
from app.services.finance_context_client import fetch_finance_context, FinanceContext


def _run_narrative_sync(explanation: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Run async generate_narrative from sync code in a thread to avoid blocking/corrupting the main event loop."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, generate_narrative(explanation))
            return future.result(timeout=30)
    except Exception:
        return None, None


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
    """Score a universe candidate; see _score_universe_candidate_breakdown for breakdown."""
    score, _ = _score_universe_candidate_breakdown(candidate, risk)
    return score


def _score_universe_candidate_breakdown(
    candidate: Dict[str, Any],
    risk: Dict[str, Any],
) -> tuple:
    """
    Score a universe candidate and return (score, breakdown_dict) for transparency.
    breakdown_dict has: base, risk_band_match, industry_match, loss_aversion_bonus, total.
    """
    base = Decimal("1.0")
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

    risk_band_match = Decimal("0")
    band_order = ("conservative", "balanced", "aggressive")
    try:
        user_idx = band_order.index(risk_tolerance)
        cand_idx = band_order.index(candidate_band)
        gap = abs(user_idx - cand_idx)
        if gap == 0:
            risk_band_match = Decimal("0.5")
        elif gap == 1:
            risk_band_match = Decimal("0.2")
        else:
            risk_band_match = Decimal("-0.4")
    except ValueError:
        pass

    industry_match = Decimal("0")
    if industries and candidate_sector in industries:
        industry_match = Decimal("0.6")
    elif industries and candidate_sector == "broad_market":
        industry_match = Decimal("0.3")
    elif not industries and candidate_sector == "broad_market":
        industry_match = Decimal("0.2")

    loss_aversion_bonus = Decimal("0")
    if loss_aversion == "high" and candidate_band == "conservative":
        loss_aversion_bonus = Decimal("0.4")
    elif loss_aversion == "low" and candidate_band == "aggressive":
        loss_aversion_bonus = Decimal("0.2")

    total = max(Decimal("0"), base + risk_band_match + industry_match + loss_aversion_bonus)
    breakdown = {
        "base": str(base),
        "risk_band_match": str(risk_band_match),
        "industry_match": str(industry_match),
        "loss_aversion_bonus": str(loss_aversion_bonus),
        "total": str(total),
        "description": "Universe score from risk band alignment, sector preference, and loss aversion.",
    }
    return total, breakdown


# Soft scoring: max total penalty so one metric does not wipe out aggressive suggestions
FINANCE_PENALTY_CAP = Decimal("0.30")
SAVINGS_RATE_THRESHOLD = 0.10
GOAL_HORIZON_MONTHS_THRESHOLD = 12
GOALS_BEHIND_PENALTY = Decimal("0.08")
MANY_GOALS_COUNT = 4


def _finance_penalty(finance_ctx: Optional[FinanceContext], risk_band: str) -> Decimal:
    """Return penalty to subtract from score when candidate/holding is aggressive or balanced and finance context suggests caution."""
    if finance_ctx is None or not finance_ctx.data_fresh:
        return Decimal("0")
    band = (risk_band or "balanced").lower()
    if band == "conservative":
        return Decimal("0")
    penalty = Decimal("0")
    if finance_ctx.savings_rate is not None and finance_ctx.savings_rate < SAVINGS_RATE_THRESHOLD:
        penalty += Decimal("0.06")
    if finance_ctx.surplus is not None and finance_ctx.surplus <= 0:
        penalty += Decimal("0.08")
    if finance_ctx.goal_horizon_months is not None and finance_ctx.goal_horizon_months < GOAL_HORIZON_MONTHS_THRESHOLD:
        penalty += Decimal("0.05")
    if finance_ctx.goals_behind:
        penalty += GOALS_BEHIND_PENALTY
    if finance_ctx.active_goals_count >= MANY_GOALS_COUNT:
        penalty += Decimal("0.03")
    if band == "balanced":
        penalty = penalty * Decimal("0.5")
    return min(penalty, FINANCE_PENALTY_CAP)


def _get_risk_band_for_symbol(symbol: str) -> str:
    """Return risk_band from analyst universe for symbol, else 'balanced'."""
    universe = get_analyst_universe()
    for c in universe:
        if (c.get("symbol") or "").strip().upper() == (symbol or "").strip().upper():
            return (c.get("risk_band") or "balanced").lower()
    return "balanced"


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

    def _run_no_holdings(
        self, user_id: int, risk: Dict[str, Any], finance_ctx: Optional[Any] = None
    ) -> Dict[str, Any]:
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
            s, breakdown = _score_universe_candidate_breakdown(c, risk)
            scored.append((s, c, breakdown))
        scored.sort(key=lambda x: x[0], reverse=True)
        top_n = min(MAX_RECOMMENDATIONS, len(scored))
        chosen = [(item, breakdown) for _, item, breakdown in scored[:top_n]]

        items_with_scores: List[Dict[str, Any]] = []
        for rank, (c, score_breakdown) in enumerate(chosen, 1):
            sym = (c.get("symbol") or "").strip().upper()
            sector = (c.get("sector") or "broad_market").replace("_", " ").title()
            risk_band = (c.get("risk_band") or "balanced").lower()
            desc = c.get("description") or sym
            # Normalize score to 0–1 range for display; use rank so higher rank = higher score
            combined = Decimal("1") - (Decimal(rank - 1) / Decimal(max(len(chosen), 1))) * Decimal("0.5")
            combined -= _finance_penalty(finance_ctx, risk_band)
            combined = max(Decimal("0"), min(Decimal("1"), combined))
            conf = Decimal("0.85") - (Decimal(rank - 1) / Decimal(max(len(chosen), 1))) * Decimal("0.2")
            conf = max(Decimal("0.5"), min(Decimal("1"), conf))

            why = [
                f"Suggested to build a diversified portfolio aligned with your risk profile ({risk.get('risk_tolerance') or 'balanced'}).",
                f"Sector: {sector}. Fits goal of seeking risk-adjusted return and avoiding unnecessary losses.",
            ]
            if risk.get("industry_preferences"):
                why.append("Matches or complements your stated industry/sector preferences.")
            if finance_ctx is not None:
                why.append("Given your current savings rate and goals, we've tilted suggestions slightly more conservative where appropriate.")
            why.append(f"Use this as a starting idea; add the symbol to Holdings when you are ready.")

            sec = get_security_info(sym) or {}
            security = {
                "full_name": sec.get("full_name") or c.get("full_name") or c.get("description") or sym,
                "sector": sec.get("sector") or sector,
                "description": sec.get("description") or desc,
                "asset_type": sec.get("asset_type") or c.get("asset_type") or "etf",
                "why_it_matters": desc + ". Low-cost diversified exposure; fits starter portfolio and risk profile.",
            }

            explanation: Dict[str, Any] = {
                "security": security,
                "why_selected": why,
                "score_breakdown": score_breakdown,
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
            if finance_ctx is not None:
                explanation["personalized_with_finance_data"] = True

            if ai_explainer_enabled():
                try:
                    narrative, narrative_provider = _run_narrative_sync(explanation)
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

    def run_for_user(self, user_id: int, auth_header: Optional[str] = None) -> Dict[str, Any]:
        """Generate recommendations, persist run + items, and return summary.
        Works with or without holdings: no holdings = suggest starter portfolio from analyst universe
        using industry/risk/Sharpe preferences to help user make money, save money, and avoid losses.
        When use_finance_data_for_recommendations is True and auth_header is provided, fetches savings/goals
        from expense service for soft scoring and narrative.
        """
        holdings_rows = self.holdings_svc.list_all_holdings_for_user(user_id)
        risk = self.risk_svc.get_risk_profile(user_id) or {}
        finance_ctx = None
        if risk.get("use_finance_data_for_recommendations") and auth_header:
            try:
                finance_ctx = fetch_finance_context(auth_header)
            except Exception:
                pass

        # No-holdings path: suggest a starter portfolio from analyst universe (preference-aware).
        if not holdings_rows:
            return self._run_no_holdings(user_id, risk, finance_ctx)

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
        held_symbols = set()
        heuristic_items: List[Dict[str, Any]] = []
        for row, w in zip(holdings_rows, weights or [Decimal("0")] * len(holdings_rows)):
            symbol = str(row.get("symbol") or "").upper()
            held_symbols.add(symbol)
            risk_tolerance = (risk.get("risk_tolerance") or "balanced").lower()
            base_score = sharpe if sharpe > 0 else Decimal("0")
            weight_penalty = Decimal("0")
            if w > Decimal("0.2"):
                weight_penalty += (w - Decimal("0.2")) * Decimal("2")
            vol_penalty = Decimal("0")
            if risk_tolerance == "conservative" and vol_annual > (risk.get("target_volatility") or Decimal("0.15")):
                vol_penalty += Decimal("0.5")
            heuristic_score = max(Decimal("0"), base_score - weight_penalty - vol_penalty)
            heuristic_items.append(
                {
                    "symbol": symbol,
                    "weight": w,
                    "heuristic_score": heuristic_score,
                    "base_score": base_score,
                    "weight_penalty": weight_penalty,
                    "vol_penalty": vol_penalty,
                }
            )

        # Stage 2: "predictive" reranker + build holdings items with score_breakdown
        items_with_scores: List[Dict[str, Any]] = []
        for item in heuristic_items:
            h_score = Decimal(str(item["heuristic_score"]))
            model_score = h_score / (Decimal("1") + abs(h_score))
            combined = (h_score * Decimal("0.7")) + (model_score * Decimal("0.3"))
            risk_band = _get_risk_band_for_symbol(item["symbol"])
            combined -= _finance_penalty(finance_ctx, risk_band)
            combined = max(Decimal("0"), combined)

            conf = Decimal("1.0")
            conf -= vol_annual * Decimal("0.5")
            conf -= hhi * Decimal("0.2")
            if conf < Decimal("0"):
                conf = Decimal("0")
            if conf > Decimal("1"):
                conf = Decimal("1")

            score_breakdown = {
                "type": "holding",
                "sharpe_contribution": str(item["base_score"]),
                "weight_penalty": str(item["weight_penalty"]),
                "volatility_penalty": str(item["vol_penalty"]),
                "heuristic_score": str(h_score),
                "model_score": str(model_score),
                "combined": str(combined),
                "description": "Holding score from portfolio Sharpe, position weight, and volatility vs risk tolerance.",
            }

            why_selected = [
                "Risk-adjusted score based on portfolio Sharpe ratio and current position weight.",
            ]
            if risk.get("risk_tolerance"):
                why_selected.append(f"Your risk tolerance ({risk.get('risk_tolerance')}) is reflected in the score.")
            if risk.get("sharpe_objective") is not None:
                why_selected.append("Compared against your target Sharpe objective to favor risk-adjusted return.")
            if finance_ctx is not None:
                why_selected.append("Given your current savings rate and goals, we've tilted suggestions slightly more conservative where appropriate.")
            why_selected.append("Aims to support making money and avoiding undue losses via diversification and weight limits.")

            sec = get_security_info(item["symbol"])
            if sec:
                security = {
                    "full_name": sec["full_name"],
                    "sector": sec["sector"],
                    "description": sec["description"],
                    "asset_type": sec["asset_type"],
                    "why_it_matters": sec.get("description") or f"Position in your portfolio; sector {sec['sector']}.",
                }
            else:
                security = {
                    "full_name": item["symbol"],
                    "sector": "—",
                    "description": "",
                    "asset_type": "unknown",
                    "why_it_matters": "",
                }

            explanation: Dict[str, Any] = {
                "security": security,
                "why_selected": why_selected,
                "score_breakdown": score_breakdown,
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
            if finance_ctx is not None:
                explanation["personalized_with_finance_data"] = True

            if ai_explainer_enabled():
                try:
                    narrative, narrative_provider = _run_narrative_sync(explanation)
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

        # Universe suggestions: score candidates not already held, take top (MAX - holdings), merge and sort
        universe = get_analyst_universe()
        universe_scored: List[tuple] = []
        for c in universe:
            sym = (c.get("symbol") or "").strip().upper()
            if not sym or sym in held_symbols:
                continue
            s, breakdown = _score_universe_candidate_breakdown(c, risk)
            universe_scored.append((s, c, breakdown))
        universe_scored.sort(key=lambda x: x[0], reverse=True)
        slots = max(0, MAX_RECOMMENDATIONS - len(items_with_scores))
        for s, c, score_breakdown in universe_scored[:slots]:
            sym = (c.get("symbol") or "").strip().upper()
            sector = (c.get("sector") or "broad_market").replace("_", " ").title()
            risk_band = (c.get("risk_band") or "balanced").lower()
            desc = c.get("description") or sym
            # Normalize for display: map raw score to 0-1 range (universe scores are typically 0.8-2.x)
            combined = min(Decimal("1"), max(Decimal("0"), (s - Decimal("0.5")) / Decimal("2")))
            combined -= _finance_penalty(finance_ctx, risk_band)
            combined = max(Decimal("0"), min(Decimal("1"), combined))
            conf = Decimal("0.75")

            why = [
                "Suggested to diversify or add exposure aligned with your risk profile.",
                f"Sector: {sector}. Fits goal of risk-adjusted return.",
            ]
            if risk.get("industry_preferences"):
                why.append("Matches or complements your stated industry/sector preferences.")
            if finance_ctx is not None:
                why.append("Given your current savings rate and goals, we've tilted suggestions slightly more conservative where appropriate.")
            why.append("Add to Holdings when ready.")

            sec = get_security_info(sym) or {}
            security = {
                "full_name": sec.get("full_name") or c.get("full_name") or c.get("description") or sym,
                "sector": sec.get("sector") or sector,
                "description": sec.get("description") or desc,
                "asset_type": sec.get("asset_type") or c.get("asset_type") or "etf",
                "why_it_matters": desc + ". Diversification or new idea; fits risk profile.",
            }
            explanation = {
                "security": security,
                "why_selected": why,
                "score_breakdown": score_breakdown,
                "key_risk_contributors": [f"risk_band={risk_band}", f"sector={sector}", "suggestion=True"],
                "risk_metrics": {"sharpe": "N/A", "volatility_annual": "N/A", "max_drawdown": "N/A", "weight": "0"},
                "data_freshness": {"provider": "analyst_universe", "stale_seconds": None},
                "confidence": {"value": float(conf), "reason": "Based on risk and sector fit."},
                "news_factors": {"sentiment_score_7d": None, "event_flags": []},
                "analyst_note": f"{desc}. Suggested to diversify or add exposure.",
            }
            if finance_ctx is not None:
                explanation["personalized_with_finance_data"] = True
            items_with_scores.append({
                "symbol": sym,
                "score": combined,
                "confidence": conf,
                "explanation_json": explanation,
            })

        # Sort all by score descending and cap at MAX_RECOMMENDATIONS
        items_with_scores.sort(key=lambda x: (x["score"], x["symbol"]), reverse=True)
        items_with_scores = items_with_scores[:MAX_RECOMMENDATIONS]

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

