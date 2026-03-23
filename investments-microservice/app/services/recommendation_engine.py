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
from app.services.analyst_universe import get_analyst_universe, get_security_info, HIGH_OVERLAP_GROUPS
from app.services.finance_context_client import fetch_finance_context, FinanceContext
from app.services.tax_harvesting_scanner import scan_harvesting_opportunities


def _get_db_context() -> Dict[str, Any]:
    """Return a DB connection context dict from config (shared by TLH scanner and others)."""
    from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
    return {
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "dbname": DB_NAME or "investments_db",
    }


def _fetch_live_prices(symbols: List[str]) -> Dict[str, Decimal]:
    """
    Fetch current prices for a list of symbols using yfinance.
    Returns {symbol: price} for every symbol that resolved successfully.
    Returns empty dict on any failure (yfinance down, network error, etc.)
    so that TLH scanning degrades gracefully rather than crashing.

    yfinance is already a declared dependency of this service; no new import needed.
    Batched via download() to minimise round-trips.
    """
    if not symbols:
        return {}
    try:
        import yfinance as yf
        # download() returns a DataFrame; 'Close' column has the latest price
        data = yf.download(
            tickers=symbols,
            period="1d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if data.empty:
            return {}
        prices: Dict[str, Decimal] = {}
        close = data["Close"] if "Close" in data.columns else data
        if len(symbols) == 1:
            # Single-ticker returns a Series, not a DataFrame
            sym = symbols[0].upper()
            val = close.iloc[-1] if hasattr(close, "iloc") else close
            try:
                prices[sym] = Decimal(str(float(val)))
            except Exception:
                pass
        else:
            for sym in symbols:
                s = sym.upper()
                if s in close.columns:
                    try:
                        prices[s] = Decimal(str(float(close[s].iloc[-1])))
                    except Exception:
                        pass
        return prices
    except Exception as exc:
        logging.getLogger("investments_recommendations").debug(
            "yfinance_price_fetch_failed: %s", exc
        )
        return {}


def _get_tlh_symbols(user_id: int) -> Dict[str, float]:
    """
    Return {symbol: harvestable_loss_dollars} for all positions with unrealized loss
    above the default threshold ($200).  Returns empty dict on any failure so that
    recommendations always succeed even if TLH data is unavailable.

    Sprint 3: live yfinance quotes are now fetched for the user's holdings before
    calling the scanner, so harvestable_loss values are based on real current prices.
    """
    try:
        ctx = _get_db_context()
        # Fetch the user's holding symbols first so we can pull prices in one batch
        from app.services.holdings_data_service import HoldingsDataService
        holdings_svc: HoldingsDataService = _get_holdings_service()
        holdings = holdings_svc.list_all_holdings_for_user(user_id)
        symbols = list({str(h.get("symbol") or "").upper() for h in holdings if h.get("symbol")})
        symbol_to_price = _fetch_live_prices(symbols)
        opps = scan_harvesting_opportunities(ctx, user_id, symbol_to_price=symbol_to_price)
        return {
            o["symbol"]: float(o["harvestable_loss"])
            for o in opps
            if not o.get("wash_sale_risk")
        }
    except Exception:
        return {}


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


def _detect_holdings_etf_overlap(held_symbols: set) -> List[Dict[str, Any]]:
    """
    Sprint 3: check the user's actual held symbols against HIGH_OVERLAP_GROUPS.

    Returns a list of overlap warnings, one per group where the user holds
    >= 2 substantially-identical ETFs.  Each warning contains:
      {
        "symbols_held":  list[str],   # the overlapping tickers the user holds
        "preferred":     str,         # lowest-cost representative from the group
        "message":       str,         # human-readable explanation
      }

    These warnings are injected into the recommendation output so the UI can
    alert the user: "You hold VOO and IVV — these track the same index.
    Consider consolidating into VOO to reduce redundancy."

    This is distinct from the universe-level deduplication in analyst_universe.py:
      - Universe dedup:   prevents *suggesting* duplicate ETFs to new users.
      - Holdings overlap: flags *existing* duplicate positions for current users.
    """
    warnings: List[Dict[str, Any]] = []
    syms_upper = {s.upper() for s in held_symbols}
    for group in HIGH_OVERLAP_GROUPS:
        held_in_group = [s for s in group if s in syms_upper]
        if len(held_in_group) >= 2:
            preferred = group[0]  # first in group is the preferred representative
            warnings.append({
                "symbols_held": held_in_group,
                "preferred": preferred,
                "message": (
                    f"You hold {' and '.join(held_in_group)}, which track substantially "
                    f"the same index. Consider consolidating into {preferred} to eliminate "
                    f"redundant exposure and simplify rebalancing."
                ),
            })
    return warnings


# ---------------------------------------------------------------------------
# Sprint 2: LightGBM reranker + SHAP explainability
# ---------------------------------------------------------------------------
# Design intent:
#   The Stage 2 "predictive" reranker was previously a sigmoid normalisation
#   of h_score — analytically identical to just using h_score with a different
#   scale.  This replaces it with a real LightGBM model.
#
#   Training strategy (knowledge distillation / self-supervised):
#   - We have no explicit user labels ("did this recommendation lead to a good
#     outcome?") so we bootstrap with synthetic labels derived from the same
#     heuristic signals that Stage 1 uses.
#   - The model learns a non-linear combination of the five features below.
#   - At inference the model score replaces the sigmoid transform; SHAP
#     TreeExplainer produces per-feature attributions used by the AI explainer.
#
#   Features:
#     0  heuristic_score     — Stage 1 output (Sharpe + penalties)
#     1  weight              — position weight in portfolio
#     2  vol_annual          — portfolio annualised volatility
#     3  hhi                 — Herfindahl concentration index
#     4  tlh_loss_scaled     — harvestable TLH loss / 5000 (0-1)
#
#   The model is trained once per recommendation run on the current holdings
#   batch (typically 5-20 items).  With so few samples, LightGBM runs in
#   milliseconds and produces a monotonically sensible score because the
#   synthetic labels are constructed to be consistent with the heuristics.
#
#   Graceful degradation: if lightgbm is not installed, falls back to the
#   previous sigmoid normalisation so nothing breaks.
# ---------------------------------------------------------------------------

import threading as _threading
_lgbm_lock = _threading.Lock()


def _lgbm_rerank(
    heuristic_items: List[Dict[str, Any]],
    vol_annual: Decimal,
    hhi: Decimal,
    tlh_symbols: Dict[str, float],
) -> Dict[str, Any]:
    """
    Train a LightGBM ranker on the current holding batch and return:
      {symbol: {"model_score": float, "shap_values": list[float]}}

    If LightGBM is unavailable returns an empty dict; caller falls back to
    the sigmoid approximation.

    Synthetic label construction:
      label = clip(heuristic_score * (1 + tlh_bonus) * diversification_factor, 0, 1)
      where diversification_factor = 1 - (weight - 0.1).clamp(0, 0.9)
    This encodes: higher Sharpe is good, concentration is bad, TLH bonus is good.
    """
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError:
        return {}

    if not heuristic_items:
        return {}

    rows = []
    labels = []
    for item in heuristic_items:
        h = float(item["heuristic_score"])
        w = float(item["weight"])
        v = float(vol_annual)
        c = float(hhi)
        tlh_raw = tlh_symbols.get(item["symbol"], 0.0)
        tlh_scaled = min(1.0, tlh_raw / 5000.0)
        rows.append([h, w, v, c, tlh_scaled])
        # Synthetic label
        div_factor = max(0.0, 1.0 - max(0.0, w - 0.10))
        tlh_bonus_factor = 1.0 + 0.1 * tlh_scaled
        label = min(1.0, max(0.0, h * div_factor * tlh_bonus_factor))
        labels.append(label)

    X = np.array(rows, dtype=np.float32)
    y = np.array(labels, dtype=np.float32)

    if len(X) < 2:
        return {}

    try:
        params = {
            "objective": "regression",
            "num_leaves": 4,
            "n_estimators": 20,
            "learning_rate": 0.1,
            "min_child_samples": 1,
            "verbose": -1,
        }
        model = lgb.LGBMRegressor(**params)
        model.fit(X, y)
        preds = model.predict(X)

        # SHAP TreeExplainer for per-feature attributions
        shap_values_all = None
        try:
            import shap
            explainer = shap.TreeExplainer(model)
            shap_values_all = explainer.shap_values(X)
        except Exception:
            pass

        feature_names = ["heuristic_score", "weight", "vol_annual", "hhi", "tlh_loss_scaled"]
        result = {}
        for idx, item in enumerate(heuristic_items):
            shap_row = None
            if shap_values_all is not None:
                shap_row = {
                    feature_names[j]: round(float(shap_values_all[idx][j]), 6)
                    for j in range(len(feature_names))
                }
            result[item["symbol"]] = {
                "model_score": float(np.clip(preds[idx], 0.0, 1.0)),
                "shap_values": shap_row,
            }
        return result
    except Exception:
        return {}


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
        self,
        user_id: int,
        risk: Dict[str, Any],
        finance_ctx: Optional[Any] = None,
        include_ai_narratives: bool = True,
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

            if include_ai_narratives and ai_explainer_enabled():
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
        zero = Decimal("0")
        port_snap = {
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
            "position_count": "0",
            "holdings_top": [],
        }
        if run_id:
            self.rec_svc.insert_items(run_id, items_with_scores)
            self.rec_svc.update_run_portfolio_snapshot(run_id, port_snap)
        return {
            "run": run,
            "items": [
                {"symbol": i["symbol"], "score": str(i["score"]), "confidence": float(i["confidence"])}
                for i in items_with_scores
            ],
            "portfolio": port_snap,
        }

    def run_for_user(
        self,
        user_id: int,
        auth_header: Optional[str] = None,
        include_ai_narratives: bool = True,
        finance_ctx: Optional[FinanceContext] = None,
    ) -> Dict[str, Any]:
        """Generate recommendations, persist run + items, and return summary.
        Works with or without holdings: no holdings = suggest starter portfolio from analyst universe
        using industry/risk/Sharpe preferences to help user make money, save money, and avoid losses.
        When use_finance_data_for_recommendations is True and auth_header is provided, fetches savings/goals
        from expense service for soft scoring and narrative.
        """
        holdings_rows = self.holdings_svc.list_all_holdings_for_user(user_id)
        risk = self.risk_svc.get_risk_profile(user_id) or {}
        if finance_ctx is None and risk.get("use_finance_data_for_recommendations") and auth_header:
            try:
                finance_ctx = fetch_finance_context(auth_header)
            except Exception:
                pass

        # No-holdings path: suggest a starter portfolio from analyst universe (preference-aware).
        if not holdings_rows:
            return self._run_no_holdings(
                user_id,
                risk,
                finance_ctx,
                include_ai_narratives=include_ai_narratives,
            )

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

        holdings_breakdown: List[Dict[str, Any]] = []
        wlist = weights or [Decimal("0")] * len(holdings_rows)
        for row, w in zip(holdings_rows, wlist):
            holdings_breakdown.append(
                {
                    "symbol": str(row.get("symbol") or "").upper(),
                    "weight": str(w),
                    "source": str(row.get("source") or "manual").lower(),
                    "quantity": str(row.get("quantity") or "0"),
                    "avg_cost": str(row.get("avg_cost") or "0"),
                }
            )
        holdings_breakdown.sort(
            key=lambda x: Decimal(str(x["weight"])) if x.get("weight") else Decimal("0"),
            reverse=True,
        )

        # Sprint 3: use full snapshot history for accurate Sharpe/vol/MDD.
        # list_snapshots() returns rows ordered ASC by snapshot_date so we
        # get a time series of total_value rather than a two-point approximation.
        # Falls back to the two-point series if fewer than 3 snapshots exist.
        try:
            from datetime import date as _date, timedelta as _timedelta
            history_from = _date.today() - _timedelta(days=365)
            snapshot_history = self.snapshot_svc.list_snapshots(
                user_id, date_from=history_from
            )
            if len(snapshot_history) >= 3:
                portfolio_values = [
                    Decimal(str(s["total_value"])) for s in snapshot_history
                ]
            else:
                portfolio_values = [total_cost_basis, total_value]
        except Exception:
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

        # Fetch TLH opportunities once for the user (best-effort; empty dict on failure).
        # Used to add a score bonus that surfaces harvestable positions for user review.
        tlh_symbols = _get_tlh_symbols(user_id)

        # Stage 2: LightGBM reranker (Sprint 2) — trains on current holding batch.
        # Falls back to sigmoid approximation if lightgbm is not installed.
        lgbm_scores = _lgbm_rerank(heuristic_items, vol_annual, hhi, tlh_symbols)

        items_with_scores: List[Dict[str, Any]] = []
        for item in heuristic_items:
            h_score = Decimal(str(item["heuristic_score"]))
            lgbm_out = lgbm_scores.get(item["symbol"])
            if lgbm_out:
                # Real LightGBM prediction
                model_score = Decimal(str(lgbm_out["model_score"]))
                model_source = "lightgbm"
            else:
                # Fallback: sigmoid normalisation (original behaviour)
                model_score = h_score / (Decimal("1") + abs(h_score))
                model_source = "sigmoid_fallback"
            combined = (h_score * Decimal("0.7")) + (model_score * Decimal("0.3"))
            risk_band = _get_risk_band_for_symbol(item["symbol"])
            combined -= _finance_penalty(finance_ctx, risk_band)
            combined = max(Decimal("0"), combined)

            # TLH bonus: +0.05 base + up to +0.05 scaled by harvestable loss (capped at $5000).
            # Rationale: users benefit from being nudged to review these positions promptly.
            # Only applied when there is no wash-sale risk (filtered in _get_tlh_symbols).
            tlh_loss = tlh_symbols.get(item["symbol"], 0.0)
            if tlh_loss > 0:
                tlh_bonus = Decimal("0.05") + min(Decimal("0.05"), Decimal(str(tlh_loss)) / Decimal("5000"))
                combined += tlh_bonus

            # Confidence: Wilson-inspired formula that maps (volatility, concentration) to [0, 1].
            # Old formula: 1.0 - 0.5*vol - 0.2*hhi  — linear, can go negative, weights uncalibrated.
            # New formula: sigmoid-like compression — each risk factor independently reduces
            # confidence multiplicatively, guaranteeing [0, 1] without clamping.
            #   conf = base * (1 / (1 + vol_penalty)) * (1 / (1 + hhi_penalty))
            # vol_annual ~ 0.15 typical → penalty ~0.075, conf multiplier ~0.93
            # hhi ~ 0.25 typical       → penalty ~0.05,  conf multiplier ~0.95
            vol_penalty = vol_annual * Decimal("0.5")
            hhi_penalty = hhi * Decimal("0.2")
            conf = Decimal("1") / (Decimal("1") + vol_penalty) * (Decimal("1") / (Decimal("1") + hhi_penalty))
            # Clamp to [0.10, 1.0] so confidence never reads as 0 for a real data point
            conf = max(Decimal("0.10"), min(Decimal("1.0"), conf))

            score_breakdown = {
                "type": "holding",
                "sharpe_contribution": str(item["base_score"]),
                "weight_penalty": str(item["weight_penalty"]),
                "volatility_penalty": str(item["vol_penalty"]),
                "heuristic_score": str(h_score),
                "model_score": str(model_score),
                "tlh_bonus": str(round(tlh_bonus, 4)) if tlh_loss > 0 else "0",
                "tlh_harvestable_loss": str(round(tlh_loss, 2)) if tlh_loss > 0 else "0",
                "model_source": model_source,
                "shap_values": lgbm_out["shap_values"] if lgbm_out else None,
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
            if tlh_loss > 0:
                why_selected.append(
                    f"This position has an estimated ${tlh_loss:,.0f} in unrealized losses eligible for "
                    "tax-loss harvesting (no wash-sale risk detected). Review for potential tax benefit."
                )
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

            if include_ai_narratives and ai_explainer_enabled():
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
        portfolio_out = {
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
            "position_count": str(len(holdings_rows)),
            "holdings_top": holdings_breakdown[:10],
            "snapshot_date": str(snapshot.get("snapshot_date"))
            if snapshot and snapshot.get("snapshot_date")
            else None,
        }
        if run_id:
            self.rec_svc.insert_items(run_id, items_with_scores)
            self.rec_svc.update_run_portfolio_snapshot(run_id, portfolio_out)
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

        # Sprint 3: detect ETF overlap in the user's actual holdings
        etf_overlap_warnings = _detect_holdings_etf_overlap(held_symbols)

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
            "portfolio": portfolio_out,
            "etf_overlap_warnings": etf_overlap_warnings,
        }

