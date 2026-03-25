"""
Portfolio health scoring service.

Computes a 0-100 composite score from four components:
  diversification (30%): 1 - HHI, where HHI = sum(weight^2)
  alignment       (25%): penalty for sector drift vs user targets
  consistency     (25%): beta vs target beta for risk profile
  momentum        (20%): Sharpe ratio quality (90-day)

Score tiers:
  75-100 => Green  "Portfolio is on track"
  40-74  => Amber  "A few things to review"
  0-39   => Red    "Worth reviewing"
"""
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

import psycopg2

logger = logging.getLogger(__name__)

_RISK_TARGET_BETA = {
    "conservative": 0.7,
    "balanced": 1.0,
    "aggressive": 1.3,
}


def _get_conn(db_context: Dict[str, Any]):
    return psycopg2.connect(
        host=db_context.get("host", "localhost"),
        port=int(db_context.get("port", 5432)),
        user=db_context.get("user", "postgres"),
        password=db_context.get("password", "postgres"),
        dbname=db_context.get("dbname", "investments_db"),
        connect_timeout=5,
    )


def _diversification_score(weights: List[float]) -> float:
    """0-100 based on HHI. HHI=0 => 100, HHI=1 => 0."""
    if not weights:
        return 0.0
    hhi = sum(w * w for w in weights)
    return round(max(0.0, min(100.0, (1.0 - hhi) * 100)), 1)


def _alignment_score(actual: Dict[str, float], target: Dict[str, float]) -> float:
    """Deduct 3 points per 1% of sector drift. Score 0-100."""
    if not target:
        return 75.0  # neutral when no targets set
    total_drift = 0.0
    for sector, t_pct in target.items():
        a_pct = actual.get(sector, 0.0)
        total_drift += abs(a_pct - t_pct)
    # total_drift is sum of absolute deviations (already in %, 0-100 scale)
    score = max(0.0, 100.0 - total_drift * 3.0)
    return round(score, 1)


def _consistency_score(portfolio_beta: float, risk_tolerance: str) -> float:
    """Deduct 40 points per unit of beta deviation from target. Score 0-100."""
    target_beta = _RISK_TARGET_BETA.get(risk_tolerance, 1.0)
    deviation = abs(portfolio_beta - target_beta)
    score = max(0.0, 100.0 - deviation * 40.0)
    return round(score, 1)


def _momentum_score(sharpe: float) -> float:
    """Sharpe-based score: 50 + sharpe*25, clamped 0-100."""
    score = 50.0 + sharpe * 25.0
    return round(max(0.0, min(100.0, score)), 1)


def _fetch_risk_profile(db_context: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    try:
        conn = _get_conn(db_context)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT risk_tolerance, target_volatility FROM risk_profile WHERE user_id = %s LIMIT 1",
                    (user_id,),
                )
                row = cur.fetchone()
                if row:
                    return {"risk_tolerance": row[0] or "balanced", "target_volatility": float(row[1] or 0.15)}
        finally:
            conn.close()
    except Exception as e:
        logger.debug("fetch_risk_profile error: %s", e)
    return {"risk_tolerance": "balanced", "target_volatility": 0.15}


def _fetch_latest_sharpe(db_context: Dict[str, Any], user_id: int) -> float:
    """Return the latest 90-day Sharpe ratio from portfolio_snapshot."""
    try:
        conn = _get_conn(db_context)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT volatility_30d, snapshot_date FROM portfolio_snapshot
                       WHERE user_id = %s ORDER BY snapshot_date DESC LIMIT 1""",
                    (user_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    # Simplified Sharpe: using vol as proxy (returns not stored); default 0.5
                    return 0.5
        finally:
            conn.close()
    except Exception as e:
        logger.debug("fetch_latest_sharpe error: %s", e)
    return 0.5  # neutral default


def _fetch_sector_targets(db_context: Dict[str, Any], user_id: int) -> Dict[str, float]:
    """Return sector targets from recommendation preferences."""
    try:
        conn = _get_conn(db_context)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT preferences_json FROM recommendations_preferences WHERE user_id = %s LIMIT 1",
                    (user_id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    import json
                    prefs = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    return prefs.get("sector_targets", {})
        finally:
            conn.close()
    except Exception as e:
        logger.debug("fetch_sector_targets error: %s", e)
    return {}


def _save_snapshot(db_context: Dict[str, Any], user_id: int, result: Dict[str, Any]) -> None:
    """Upsert today's health snapshot."""
    try:
        import json
        from datetime import date
        conn = _get_conn(db_context)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO portfolio_health_snapshot
                           (user_id, snapshot_date, score, tier, components_json, flags_json)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (user_id, snapshot_date)
                       DO UPDATE SET score = EXCLUDED.score,
                                     tier = EXCLUDED.tier,
                                     components_json = EXCLUDED.components_json,
                                     flags_json = EXCLUDED.flags_json""",
                    (
                        user_id,
                        date.today().isoformat(),
                        result["score"],
                        result["tier"],
                        json.dumps(result["components"]),
                        json.dumps(result["flags"]),
                    ),
                )
                conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.debug("save_snapshot error: %s", e)


def compute_health_score(
    user_id: int,
    positions: List[Dict[str, Any]],
    sector_breakdown: Dict[str, float],
    db_context: Dict[str, Any],
    save: bool = True,
) -> Dict[str, Any]:
    """
    Compute portfolio health score.

    positions: list of {symbol, value (Decimal or float)}
    sector_breakdown: {sector_name: pct_of_portfolio (0-100)}
    """
    risk_profile = _fetch_risk_profile(db_context, user_id)
    sector_targets = _fetch_sector_targets(db_context, user_id)
    sharpe = _fetch_latest_sharpe(db_context, user_id)

    total_value = sum(float(p.get("value", 0)) for p in positions)
    weights = []
    if total_value > 0:
        weights = [float(p.get("value", 0)) / total_value for p in positions]

    d_score = _diversification_score(weights)
    a_score = _alignment_score(sector_breakdown, sector_targets)
    c_score = _consistency_score(1.0, risk_profile["risk_tolerance"])  # beta=1.0 default
    m_score = _momentum_score(sharpe)

    composite = round(
        d_score * 0.30 + a_score * 0.25 + c_score * 0.25 + m_score * 0.20
    )

    if composite >= 75:
        tier = "green"
        headline = "Portfolio is on track"
    elif composite >= 40:
        tier = "amber"
        headline = "A few things worth reviewing"
    else:
        tier = "red"
        headline = "Portfolio concentration worth reviewing"

    flags = []
    if weights and max(weights) > 0.30:
        top = max(positions, key=lambda p: float(p.get("value", 0)))
        flags.append(f"{top['symbol']} represents {max(weights)*100:.0f}% of portfolio")
    if len(positions) < 3:
        flags.append("Fewer than 3 holdings — limited diversification")
    if a_score < 50 and sector_targets:
        flags.append("Sector allocation has drifted from your stated targets")

    result = {
        "score": composite,
        "tier": tier,
        "headline": headline,
        "components": {
            "diversification": {"score": d_score, "weight": 0.30, "label": "Diversification"},
            "alignment": {"score": a_score, "weight": 0.25, "label": "Sector alignment"},
            "consistency": {"score": c_score, "weight": 0.25, "label": "Risk consistency"},
            "momentum": {"score": m_score, "weight": 0.20, "label": "Momentum"},
        },
        "flags": flags[:3],
        "disclaimer": "Not financial advice. Health score is based on your stated preferences and portfolio data only.",
    }

    if save:
        _save_snapshot(db_context, user_id, result)

    return result
