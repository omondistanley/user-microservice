"""
Risk profile API: get/update user preferences for recommendations (risk tolerance,
industry/sector, Sharpe objective, loss aversion). Used by the analyst-style
recommendation engine to tailor suggestions for making money, saving money, and avoiding losses.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user_id
from app.services.risk_profile_service import RiskProfileDataService
from app.services.service_factory import ServiceFactory
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/v1", tags=["risk-profile"])


class RiskProfileUpdate(BaseModel):
    """Body for PUT /api/v1/risk-profile. All fields optional."""
    risk_tolerance: Optional[str] = Field(None, description="conservative | balanced | aggressive")
    horizon_years: Optional[int] = Field(None, ge=0, le=50)
    liquidity_needs: Optional[str] = Field(None, max_length=128)
    target_volatility: Optional[float] = Field(None, ge=0, le=1)
    industry_preferences: Optional[List[str]] = Field(
        None,
        description="Preferred sectors, e.g. technology, healthcare, broad_market, bonds",
    )
    sharpe_objective: Optional[float] = Field(None, description="Target Sharpe ratio")
    loss_aversion: Optional[str] = Field(None, description="moderate | low | high")
    use_finance_data_for_recommendations: Optional[bool] = Field(
        None,
        description="When true, use savings, goals, expenses, and budget to personalize recommendations.",
    )

    @field_validator("sharpe_objective", mode="before")
    @classmethod
    def coerce_sharpe(cls, v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except ValueError:
                return None
        return None

    @field_validator("industry_preferences", mode="before")
    @classmethod
    def coerce_industry_preferences(cls, v: Any) -> Optional[List[str]]:
        if v is None:
            return None
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return None


def _get_risk_profile_service() -> RiskProfileDataService:
    svc = ServiceFactory.get_service("RiskProfileDataService")
    if not isinstance(svc, RiskProfileDataService):
        raise RuntimeError("RiskProfileDataService not available")
    return svc


@router.get("/risk-profile", response_model=dict)
async def get_risk_profile(
    user_id: int = Depends(get_current_user_id),
    svc: RiskProfileDataService = Depends(_get_risk_profile_service),
) -> Dict[str, Any]:
    """Return the current user risk profile (preferences for recommendations)."""
    profile = svc.get_risk_profile(user_id)
    if not profile:
        return {
            "user_id": user_id,
            "risk_tolerance": "balanced",
            "horizon_years": None,
            "liquidity_needs": None,
            "target_volatility": None,
            "industry_preferences": [],
            "sharpe_objective": None,
            "loss_aversion": "moderate",
            "use_finance_data_for_recommendations": False,
        }
    out = dict(profile)
    if out.get("industry_preferences") is None:
        out["industry_preferences"] = []
    if out.get("use_finance_data_for_recommendations") is None:
        out["use_finance_data_for_recommendations"] = False
    return out


@router.put("/risk-profile", response_model=dict)
async def update_risk_profile(
    payload: RiskProfileUpdate,
    user_id: int = Depends(get_current_user_id),
    svc: RiskProfileDataService = Depends(_get_risk_profile_service),
) -> Dict[str, Any]:
    """Update risk profile. Used to tailor analyst recommendations (industry, risk/return, Sharpe, loss aversion)."""
    try:
        return svc.upsert_risk_profile(
            user_id=user_id,
            risk_tolerance=payload.risk_tolerance,
            horizon_years=payload.horizon_years,
            liquidity_needs=payload.liquidity_needs,
            target_volatility=payload.target_volatility,
            industry_preferences=payload.industry_preferences,
            sharpe_objective=payload.sharpe_objective,
            loss_aversion=payload.loss_aversion,
            use_finance_data_for_recommendations=payload.use_finance_data_for_recommendations,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
