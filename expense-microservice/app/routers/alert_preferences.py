"""User alert preferences (e.g. low_projected_balance threshold)."""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_current_user_id
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1/alert-preferences", tags=["alert-preferences"])


def _get_data_service():
    return ServiceFactory.get_service("ExpenseDataService")


class LowProjectedBalanceUpdate(BaseModel):
    threshold_value: Optional[float] = None


@router.get("/low-projected-balance")
async def get_low_projected_balance_preference(
    user_id: int = Depends(get_current_user_id),
):
    """Get the user's low projected balance threshold (minimum acceptable balance in 30 days)."""
    ds = _get_data_service()
    pref = ds.get_alert_preference(user_id, "low_projected_balance")
    if not pref:
        return {"alert_type": "low_projected_balance", "threshold_value": None}
    return {
        "alert_type": pref["alert_type"],
        "threshold_value": float(pref["threshold_value"]) if pref.get("threshold_value") is not None else None,
    }


@router.patch("/low-projected-balance")
async def set_low_projected_balance_preference(
    body: LowProjectedBalanceUpdate,
    user_id: int = Depends(get_current_user_id),
):
    """
    Set or clear the low projected balance threshold.
    When projected balance (30 days) falls below this value, a notification is sent (at most once per day).
    Pass threshold_value: null to disable.
    """
    value = Decimal(str(body.threshold_value)) if body.threshold_value is not None else None
    if value is not None and value < 0:
        raise HTTPException(status_code=400, detail="threshold_value must be non-negative")
    ds = _get_data_service()
    row = ds.set_alert_preference(user_id, "low_projected_balance", value)
    return {
        "alert_type": row.get("alert_type", "low_projected_balance"),
        "threshold_value": float(row["threshold_value"]) if row.get("threshold_value") is not None else None,
    }
