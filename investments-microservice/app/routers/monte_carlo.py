"""
Monte Carlo scenario modelling endpoint.
Returns percentile outcome paths and goal probability.
Projections are illustrative only. Not financial advice.
"""
import logging
import math
import random
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["scenario"])


def _run_monte_carlo(
    initial_value: float,
    monthly_contribution: float,
    years: int,
    return_assumption: float = 0.07,
    volatility: float = 0.15,
    n_paths: int = 1000,
    goal_amount: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Lognormal Monte Carlo simulation.
    Returns percentile outcomes and 20 sample paths for fan chart rendering.
    """
    random.seed(42)  # Deterministic for same inputs
    mu_monthly = return_assumption / 12
    sigma_monthly = volatility / math.sqrt(12)
    months = years * 12

    final_values: List[float] = []
    sample_paths: List[List[float]] = []
    sample_indices = set(random.sample(range(n_paths), min(20, n_paths)))

    for path_idx in range(n_paths):
        value = initial_value
        path_points = [round(value, 2)] if path_idx in sample_indices else None
        for _ in range(months):
            z = random.gauss(0, 1)
            monthly_return = math.exp((mu_monthly - sigma_monthly ** 2 / 2) + sigma_monthly * z) - 1
            value = value * (1 + monthly_return) + monthly_contribution
            if value < 0:
                value = 0
            if path_points is not None:
                path_points.append(round(value, 2))
        final_values.append(value)
        if path_idx in sample_indices:
            sample_paths.append(path_points)

    final_values.sort()

    def percentile(values, p):
        idx = max(0, min(len(values) - 1, int(len(values) * p / 100)))
        return round(values[idx], 2)

    p5 = percentile(final_values, 5)
    p25 = percentile(final_values, 25)
    p50 = percentile(final_values, 50)
    p75 = percentile(final_values, 75)
    p95 = percentile(final_values, 95)

    goal_probability = None
    if goal_amount and goal_amount > 0:
        goal_probability = round(sum(1 for v in final_values if v >= goal_amount) / n_paths * 100, 1)

    return {
        "p5": p5, "p25": p25, "p50": p50, "p75": p75, "p95": p95,
        "goal_probability": goal_probability,
        "sample_paths": sample_paths,
        "paths_count": n_paths,
        "months": months,
    }


@router.get("/scenario/monte-carlo", response_model=dict)
async def monte_carlo(
    user_id: int = Depends(get_current_user_id),
    initial_value: float = Query(10000.0, ge=0),
    monthly_contribution: float = Query(500.0, ge=0),
    years: int = Query(20, ge=1, le=50),
    return_pct: float = Query(7.0, ge=0, le=30, description="Annual return assumption (%)"),
    volatility_pct: float = Query(15.0, ge=1, le=50, description="Annual volatility assumption (%)"),
    goal_amount: Optional[float] = Query(None, ge=0),
):
    """
    Monte Carlo projection with 1,000 paths.
    Always shows P5 alongside P95 — never cherry-picks optimistic scenarios.
    Projections are illustrative only. Not financial advice.
    """
    result = _run_monte_carlo(
        initial_value=initial_value,
        monthly_contribution=monthly_contribution,
        years=years,
        return_assumption=return_pct / 100,
        volatility=volatility_pct / 100,
        n_paths=1000,
        goal_amount=goal_amount,
    )

    return {
        **result,
        "assumptions": {
            "initial_value": initial_value,
            "monthly_contribution": monthly_contribution,
            "years": years,
            "return_pct": return_pct,
            "volatility_pct": volatility_pct,
            "goal_amount": goal_amount,
        },
        "disclaimer": (
            "Projections are illustrative estimates based on historical averages and the assumptions shown. "
            "Actual results will differ. Past performance does not guarantee future results. "
            "This is not financial advice."
        ),
    }
