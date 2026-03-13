"""Phase 4: Forecast and anomaly insights API."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user_id
from app.services.insights_service import InsightsService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["insights"])


def _get_insights_service() -> InsightsService:
    svc = ServiceFactory.get_service("InsightsService")
    if not isinstance(svc, InsightsService):
        raise RuntimeError("InsightsService not available")
    return svc


@router.get("/insights/forecast/spend")
async def forecast_spend(
    user_id: int = Depends(get_current_user_id),
    months_back: int = Query(6, ge=1, le=24),
    category_code: Optional[int] = Query(None),
    household_id: Optional[str] = Query(None),
):
    svc = _get_insights_service()
    return svc.forecast_spend(user_id, months_back=months_back, category_code=category_code, household_id=household_id)


@router.get("/insights/anomalies")
async def get_anomalies(
    user_id: int = Depends(get_current_user_id),
    household_id: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
):
    svc = _get_insights_service()
    return {"anomalies": svc.detect_anomalies(user_id, household_id=household_id, limit=limit)}


@router.post("/insights/anomalies/{expense_id}/feedback")
async def anomaly_feedback(
    expense_id: str,
    user_id: int = Depends(get_current_user_id),
    feedback: str = Query(..., pattern="^(valid|ignore)$"),
):
    try:
        from uuid import UUID
        UUID(expense_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expense_id")
    svc = _get_insights_service()
    svc.set_anomaly_feedback(user_id, expense_id, feedback)
    return {"expense_id": expense_id, "feedback": feedback}
