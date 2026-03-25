"""
Windfall detection — surplus spike analysis.
All output is informational only — not financial advice.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.core.dependencies import get_current_user_id

router = APIRouter(prefix="/api/v1", tags=["windfall"])

DISCLAIMER = "Not financial advice. For informational purposes only."

DCA_HORIZON_MONTHS = [3, 6, 12]


def _dca_schedule(amount: float, months: int) -> list:
    monthly = round(amount / months, 2)
    return [{"month": i + 1, "amount": monthly} for i in range(months)]


@router.get("/windfall/analysis", response_model=dict)
async def windfall_analysis(
    windfall_amount: float = Query(..., gt=0, description="One-time surplus amount"),
    monthly_surplus_avg: float = Query(..., gt=0, description="3-month average monthly surplus"),
    user_id: int = Depends(get_current_user_id),
):
    """
    Returns lump-sum vs DCA comparison for a windfall amount.
    Uses 3x the average monthly surplus as the windfall threshold.
    """
    threshold = monthly_surplus_avg * 3
    is_windfall = windfall_amount >= threshold

    lump_sum_note = (
        "Investing a lump sum immediately is one approach — "
        "historically, lump-sum investing has outperformed DCA in about two-thirds of observed periods "
        "(based on published market research). Past performance does not predict future results."
    )

    dca_options = {
        f"{m}_month_dca": {
            "months": m,
            "monthly_amount": round(windfall_amount / m, 2),
            "schedule": _dca_schedule(windfall_amount, m),
            "note": f"Spreading investment over {m} months is one approach to reduce timing risk.",
        }
        for m in DCA_HORIZON_MONTHS
    }

    return {
        "windfall_amount": windfall_amount,
        "monthly_surplus_avg": monthly_surplus_avg,
        "threshold": threshold,
        "is_windfall": is_windfall,
        "lump_sum": {
            "amount": windfall_amount,
            "note": lump_sum_note,
        },
        "dca_options": dca_options,
        "disclaimer": DISCLAIMER,
    }
