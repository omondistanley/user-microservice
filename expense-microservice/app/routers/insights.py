"""Phase 4: Forecast and anomaly insights API.

Sprint 2 additions:
  - GET  /insights/anomalies/isolation-forest  — multi-dimensional IF anomaly pass
  - POST /insights/classifier/correction       — store a user category correction
  - GET  /insights/classifier/corrections      — list recent corrections for a user
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

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


@router.get("/insights/health-score")
async def get_health_score(
    savings_rate: float = Query(..., description="(income - spend) / income, e.g. 0.15 for 15%"),
    budget_adherence: float = Query(..., ge=0.0, le=2.0, description="1.0 = on budget, 0.0 = fully over"),
    spend_trend: float = Query(..., ge=-1.0, le=1.0, description="Normalised monthly spend slope (-1 rising fast, +1 falling)"),
    emergency_fund_months: float = Query(..., ge=0.0, description="Months of expenses covered by liquid savings"),
    goal_progress: float = Query(..., ge=0.0, le=1.0, description="Fraction of active goals on-pace"),
    user_id: int = Depends(get_current_user_id),
):
    """
    Compute a 0-100 Financial Health Score from five client-supplied components.

    Weights (CFPB Financial Well-Being Scale):
      savings_rate 30%, budget_adherence 25%, spend_trend 15%,
      emergency_fund_months 20%, goal_progress 10%.
    """
    return InsightsService.compute_financial_health_score(
        savings_rate=savings_rate,
        budget_adherence=budget_adherence,
        spend_trend=spend_trend,
        emergency_fund_months=emergency_fund_months,
        goal_progress=goal_progress,
    )


@router.get("/insights/anomalies/isolation-forest")
async def get_anomalies_isolation_forest(
    user_id: int = Depends(get_current_user_id),
    household_id: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    contamination: float = Query(0.05, ge=0.01, le=0.20, description="Expected fraction of anomalies (1%-20%)"),
):
    """
    Multi-dimensional anomaly detection using Isolation Forest (scikit-learn).

    Features: amount, day-of-week, day-of-month, category_code.
    Catches behavioural anomalies that per-category IQR misses
    (e.g. a normal-sized charge at an unusual time from a rare category).

    Falls back to the IQR method if scikit-learn is not installed.
    """
    svc = _get_insights_service()
    return {
        "anomalies": svc.detect_anomalies_isolation_forest(
            user_id,
            household_id=household_id,
            limit=limit,
            contamination=contamination,
        )
    }


class ClassifierCorrectionRequest(BaseModel):
    merchant_text: str = Field(..., max_length=512, description="Normalised merchant+note text that was misclassified")
    original_category_code: int
    original_category_name: str = Field(..., max_length=64)
    original_source: str = Field("keyword", pattern="^(keyword|fuzzy|embedding|user_override|plaid)$")
    original_confidence: float = Field(1.0, ge=0.0, le=1.0)
    corrected_category_code: int
    corrected_category_name: str = Field(..., max_length=64)


@router.post("/insights/classifier/correction", status_code=201)
async def store_classifier_correction(
    body: ClassifierCorrectionRequest,
    user_id: int = Depends(get_current_user_id),
):
    """
    Store a user correction to the transaction classifier.

    This creates gold-label training data. The correction is immediately
    available for future classifications of the same merchant_text for this user
    (tier-0 user_override takes precedence over all classifier tiers).
    """
    svc = _get_insights_service()
    svc.store_classifier_correction(
        user_id=user_id,
        merchant_text=body.merchant_text,
        original_category_code=body.original_category_code,
        original_category_name=body.original_category_name,
        original_source=body.original_source,
        original_confidence=body.original_confidence,
        corrected_category_code=body.corrected_category_code,
        corrected_category_name=body.corrected_category_name,
    )
    return {"stored": True, "merchant_text": body.merchant_text.strip().lower()}


@router.get("/insights/classifier/corrections")
async def list_classifier_corrections(
    user_id: int = Depends(get_current_user_id),
    limit: int = Query(100, ge=1, le=500),
):
    """Return recent classifier corrections for the authenticated user."""
    svc = _get_insights_service()
    return {"corrections": svc.list_user_corrections(user_id, limit=limit)}


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
