"""
Deterministic rebalance planning logic for the investments microservice.

Planner turns:
  - current holdings
  - ranked recommendation items (symbol/score/confidence)
  - optional previous rebalance session snapshot
  - optional finance context (goal horizon / behind goals)
into:
  - scenario choice (scenario2 vs scenario1 vs no_action)
  - sell list (hysteresis + min hold + sell cooldown + caps)
  - buy list (confidence gate + max changes + allocation weights)
  - deterministic `why_lines` for the click-to-open notification modal
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.services.finance_context_client import FinanceContext
from app.services.recommendation_evidence import finance_context_summary_lines


@dataclass(frozen=True)
class RebalanceChurnParams:
    # Threshold set A (for small $50/$100 cash account).
    min_hold_days: int = 18
    confidence_min: Decimal = Decimal("0.62")
    delta_strength_min: Decimal = Decimal("0.10")
    n_keep: int = 8
    n_buy: int = 5
    max_sells_per_rebalance: int = 2
    max_position_changes_per_rebalance: int = 3
    sell_cooldown_days: int = 5

    # Execution hint: very high confidence => market order, otherwise limit.
    market_confidence_threshold: Decimal = Decimal("0.75")


DEFAULT_PARAMS = RebalanceChurnParams()


def _as_date(dt: Any) -> Optional[date]:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    if isinstance(dt, datetime):
        return dt.date()
    # Best effort parsing for JSON-loaded timestamps.
    if isinstance(dt, str):
        try:
            # Handles ISO like 2026-03-20T12:34:56+00:00
            return datetime.fromisoformat(dt.replace("Z", "+00:00")).date()
        except Exception:
            return None
    return None


def _safe_decimal(x: Any) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")


def _jaccard_strength(a: List[str], b: List[str]) -> Decimal:
    """Return 1 - overlap_ratio in [0,1]. If a is empty, treat as full change."""
    if not a:
        return Decimal("1")
    if not b:
        return Decimal("1")
    sa = set(a)
    sb = set(b)
    inter = len(sa.intersection(sb))
    denom = max(1, len(sa))
    overlap_ratio = Decimal(str(inter)) / Decimal(str(denom))
    strength = Decimal("1") - overlap_ratio
    if strength < 0:
        return Decimal("0")
    if strength > 1:
        return Decimal("1")
    return strength


def _score_strength(intersection: List[str], new_scores: Dict[str, Decimal], prev_scores: Dict[str, Decimal]) -> Decimal:
    """
    Mean relative score change for intersecting symbols, mapped to [0,1].
    Deterministic and tolerant of missing values.
    """
    if not intersection:
        return Decimal("0")
    deltas: List[Decimal] = []
    for sym in intersection:
        prev = prev_scores.get(sym)
        new = new_scores.get(sym)
        if prev is None or new is None:
            continue
        base = prev.copy_abs()
        if base == 0:
            base = Decimal("0.0001")
        deltas.append((new - prev).copy_abs() / base)
    if not deltas:
        return Decimal("0")
    avg = sum(deltas, Decimal("0")) / Decimal(str(len(deltas)))
    # Cap to [0,1] for stable thresholds.
    if avg > 1:
        return Decimal("1")
    return avg


def _rank_map(items_ranked: List[Dict[str, Any]]) -> Dict[str, int]:
    rank: Dict[str, int] = {}
    for idx, it in enumerate(items_ranked):
        sym = str(it.get("symbol") or "").upper()
        if not sym:
            continue
        # 1-based ranking (rank 1 = best score)
        rank[sym] = idx + 1
    return rank


def _allocation_weights(buys: List[Dict[str, Any]]) -> Dict[str, Decimal]:
    """
    Normalize scores for allocation weights. Returns per-symbol weight in [0,1].
    """
    scores = [_safe_decimal(b.get("score")) for b in buys]
    total = sum(scores, Decimal("0"))
    out: Dict[str, Decimal] = {}
    if total <= 0:
        for b in buys:
            out[str(b.get("symbol")).upper()] = Decimal("0")
        return out
    for b in buys:
        sym = str(b.get("symbol") or "").upper()
        out[sym] = _safe_decimal(b.get("score")) / total
    return out


class RebalancePlanner:
    def __init__(self, churn_params: RebalanceChurnParams = DEFAULT_PARAMS) -> None:
        self.params = churn_params

    def plan(
        self,
        *,
        now_utc: datetime,
        trigger_type: str,
        holdings_rows: List[Dict[str, Any]],
        items_ranked: List[Dict[str, Any]],
        prev_session_payload: Optional[Dict[str, Any]] = None,
        last_sell_completed_at: Optional[Any] = None,
        force_scenario1: bool = False,
        target_scenario: Optional[str] = None,
        finance_ctx: Optional[FinanceContext] = None,
    ) -> Dict[str, Any]:
        """
        Returns planner output suitable for persisting into portfolio_rebalance_session.payload_json.
        """
        as_of: date = now_utc.date()
        rank_map = _rank_map(items_ranked)

        why_lines: List[str] = []
        why_lines.append(f"Trigger: {trigger_type}. Force Scenario 1: {force_scenario1}.")
        if finance_ctx:
            why_lines.extend(finance_context_summary_lines(finance_ctx))

        # Extract previous snapshot for material-change scoring.
        prev_top_buy_symbols: List[str] = []
        prev_top_buy_scores: Dict[str, Decimal] = {}
        if prev_session_payload and isinstance(prev_session_payload, dict):
            prev_top_buy_symbols = [str(s).upper() for s in (prev_session_payload.get("top_buy_symbols") or []) if str(s).strip()]
            prev_scores_raw = prev_session_payload.get("top_buy_scores") or {}
            if isinstance(prev_scores_raw, dict):
                for k, v in prev_scores_raw.items():
                    prev_top_buy_scores[str(k).upper()] = _safe_decimal(v)

        # Determine new top candidates (before scenario gating).
        held_symbols = {str(h.get("symbol") or "").upper() for h in holdings_rows if h.get("symbol")}
        # Rank-ordered items_ranked is expected from jobs; if not, planner still uses the list order.
        top_buy_candidates: List[Dict[str, Any]] = []
        for it in items_ranked:
            sym = str(it.get("symbol") or "").upper()
            if not sym or sym in held_symbols:
                continue
            conf = _safe_decimal(it.get("confidence"))
            # Material-change should not require confidence gating; still, cap to n_keep/n_buy to keep cost/complexity stable.
            if len(top_buy_candidates) >= self.params.n_buy * 2:
                break
            top_buy_candidates.append(it)

        # Keep a deterministic slice for material change and notifications.
        new_top_buy_symbols: List[str] = []
        new_top_buy_scores: Dict[str, Decimal] = {}
        new_top_buy_confidences: List[Decimal] = []
        for it in top_buy_candidates:
            sym = str(it.get("symbol") or "").upper()
            if not sym:
                continue
            new_top_buy_symbols.append(sym)
            new_top_buy_scores[sym] = _safe_decimal(it.get("score"))
            new_top_buy_confidences.append(_safe_decimal(it.get("confidence")))
            if len(new_top_buy_symbols) >= self.params.n_buy:
                break

        top_candidate_confidence = max(new_top_buy_confidences, default=Decimal("0"))
        why_lines.append(f"Top candidate confidence (best among new buys): {top_candidate_confidence}.")

        # Material change strength:
        overlap_strength = _jaccard_strength(prev_top_buy_symbols, new_top_buy_symbols)
        intersection = list(set(prev_top_buy_symbols).intersection(set(new_top_buy_symbols)))
        score_strength = _score_strength(intersection, new_top_buy_scores, prev_top_buy_scores)
        material_change_strength = (overlap_strength * Decimal("0.7")) + (score_strength * Decimal("0.3"))
        material_change_strength = min(Decimal("1"), max(Decimal("0"), material_change_strength))
        why_lines.append(
            "Material change strength computed from top-buy overlap and score deltas "
            f"(overlap={overlap_strength}, score_strength={score_strength}, total={material_change_strength})."
        )

        confidence_gate_pass = top_candidate_confidence >= self.params.confidence_min
        if confidence_gate_pass:
            why_lines.append(f"Confidence gate: PASS (>= {self.params.confidence_min}).")
        else:
            why_lines.append(f"Confidence gate: FAIL (< {self.params.confidence_min}); no buys/sells planned.")

        scenario: str = "no_action"
        if confidence_gate_pass:
            if target_scenario in ("scenario1", "scenario2"):
                scenario = target_scenario
                why_lines.append(
                    f"Target scenario selected for this phase ({scenario}); bypassing material-change gating on this phase."
                )
            elif force_scenario1:
                scenario = "scenario1"
                why_lines.append(
                    "Scenario 1 forced: bypassing material-change gate while still enforcing churn-control constraints."
                )
            else:
                if material_change_strength >= self.params.delta_strength_min:
                    scenario = "scenario2"
                    why_lines.append(
                        f"Scenario 2 material-change gate: PASS ({material_change_strength} >= {self.params.delta_strength_min})."
                    )
                else:
                    scenario = "no_action"
                    why_lines.append(
                        f"Scenario 2 material-change gate: FAIL ({material_change_strength} < {self.params.delta_strength_min}); no action."
                    )

        # If we are not acting, still output the top symbols for UI traceability.
        if scenario == "no_action":
            return {
                "scenario": scenario,
                "material_change_strength": str(material_change_strength),
                "top_candidate_confidence": str(top_candidate_confidence),
                "why_lines": why_lines,
                "sell_orders": [],
                "buy_orders": [],
                "top_buy_symbols": new_top_buy_symbols,
                "top_buy_scores": {k: str(v) for k, v in new_top_buy_scores.items()},
            }

        # Sell planning: hysteresis + min hold + sell cooldown + sell caps.
        last_sell_date = _as_date(last_sell_completed_at)
        if last_sell_date:
            days_since_sell = (as_of - last_sell_date).days
            why_lines.append(f"Last sell completed at {last_sell_date} (age: {days_since_sell} days).")
        else:
            days_since_sell = None
            why_lines.append("Last sell completed at: unknown/none; sell cooldown treated as satisfied.")

        sell_cooldown_ok = True
        if days_since_sell is not None:
            sell_cooldown_ok = days_since_sell >= self.params.sell_cooldown_days
            if sell_cooldown_ok:
                why_lines.append(f"Sell cooldown: PASS (>= {self.params.sell_cooldown_days} days).")
            else:
                why_lines.append(f"Sell cooldown: FAIL (< {self.params.sell_cooldown_days} days); blocking sells.")

        sell_eligibles: List[Dict[str, Any]] = []
        sell_blocked: List[str] = []

        for h in holdings_rows:
            sym = str(h.get("symbol") or "").upper()
            if not sym:
                continue
            rank = rank_map.get(sym)
            if rank is None:
                # If the symbol is missing from ranking, treat as worst rank and sell-eligible.
                rank = 999999
            created_at = h.get("created_at") or h.get("purchase_date")
            created_date = _as_date(created_at)
            holding_age_days = (as_of - created_date).days if created_date else None

            if holding_age_days is not None and holding_age_days < self.params.min_hold_days:
                sell_blocked.append(
                    f"{sym}: BLOCK sell (min hold {holding_age_days} < {self.params.min_hold_days} days)."
                )
                continue

            # Hysteresis: sell only if outside keep-band.
            outside_keep = rank > self.params.n_keep
            if not outside_keep:
                sell_blocked.append(f"{sym}: KEEP (rank {rank} <= N_KEEP {self.params.n_keep}).")
                continue

            if not sell_cooldown_ok:
                sell_blocked.append(f"{sym}: BLOCK sell (sell cooldown not satisfied).")
                continue

            sell_eligibles.append(
                {
                    "symbol": sym,
                    "rank": int(rank),
                    "holding_id": h.get("holding_id"),
                    "qty": h.get("quantity"),
                    "age_days": holding_age_days,
                }
            )

        # Capture blocked decisions in why_lines for transparency.
        why_lines.extend(sell_blocked[:20])

        # Select sells deterministically: biggest deviation from keep-band first.
        sell_eligibles.sort(key=lambda x: (x["rank"] - self.params.n_keep, x["symbol"]), reverse=True)
        planned_sells = sell_eligibles[: self.params.max_sells_per_rebalance]
        if planned_sells:
            why_lines.append(
                f"Planned sells (max {self.params.max_sells_per_rebalance}): {[s['symbol'] for s in planned_sells]}."
            )
        else:
            why_lines.append("No sells planned after applying hysteresis/min-hold/sell-cooldown.")

        # Buy planning: confidence gate + rank ordering + position change caps.
        # Build eligible buys from items_ranked (excluding held symbols).
        buy_candidates: List[Dict[str, Any]] = []
        for it in items_ranked:
            sym = str(it.get("symbol") or "").upper()
            if not sym or sym in held_symbols:
                continue
            conf = _safe_decimal(it.get("confidence"))
            if conf < self.params.confidence_min:
                continue
            buy_candidates.append(
                {
                    "symbol": sym,
                    "rank": rank_map.get(sym, 999999),
                    "score": _safe_decimal(it.get("score")),
                    "confidence": conf,
                }
            )
            if len(buy_candidates) >= self.params.n_buy * 2:
                break

        buy_candidates.sort(key=lambda x: (x["score"], x["confidence"], x["symbol"]), reverse=True)

        max_new_buys = max(0, self.params.max_position_changes_per_rebalance - len(planned_sells))
        target_buys = min(self.params.n_buy, max_new_buys)
        planned_buys = buy_candidates[:target_buys]

        if planned_buys:
            buy_syms = [b["symbol"] for b in planned_buys]
            why_lines.append(
                f"Planned buys (confidence>= {self.params.confidence_min}, capped by max_position_changes): {buy_syms}."
            )
        else:
            why_lines.append("No buys planned after applying confidence and churn caps.")

        alloc = _allocation_weights(planned_buys)
        buy_orders: List[Dict[str, Any]] = []
        for b in planned_buys:
            conf = _safe_decimal(b.get("confidence"))
            order_type = "market" if conf >= self.params.market_confidence_threshold else "limit"
            buy_orders.append(
                {
                    "symbol": b["symbol"],
                    "rank": int(b["rank"]),
                    "score": str(b["score"]),
                    "confidence": str(conf),
                    "allocation_weight": str(alloc.get(b["symbol"], Decimal("0"))),
                    "order_type": order_type,
                }
            )

        sell_orders: List[Dict[str, Any]] = []
        for s in planned_sells:
            sell_orders.append(
                {
                    "symbol": s["symbol"],
                    "rank": s["rank"],
                    "holding_id": s["holding_id"],
                    "qty": str(s.get("qty") or "0"),
                    "order_type": "market",  # sells first; we want deterministic liquidity
                }
            )

        why_lines.append(
            f"Summary: scenario={scenario}, sell_count={len(sell_orders)}, buy_count={len(buy_orders)}, "
            f"max_position_changes={self.params.max_position_changes_per_rebalance}."
        )

        return {
            "scenario": scenario,
            "material_change_strength": str(material_change_strength),
            "top_candidate_confidence": str(top_candidate_confidence),
            "why_lines": why_lines,
            "sell_orders": sell_orders,
            "buy_orders": buy_orders,
            "top_buy_symbols": new_top_buy_symbols,
            "top_buy_scores": {k: str(v) for k, v in new_top_buy_scores.items()},
        }

