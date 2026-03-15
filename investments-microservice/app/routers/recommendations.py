import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user_id
from app.services.recommendation_data_service import RecommendationDataService
from app.services.recommendation_engine import RecommendationEngine
from app.services.service_factory import ServiceFactory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["recommendations"])


def _get_engine() -> RecommendationEngine:
    return RecommendationEngine()


def _get_rec_data_service() -> RecommendationDataService:
    ds = ServiceFactory.get_service("RecommendationDataService")
    assert isinstance(ds, RecommendationDataService)
    return ds


@router.post("/recommendations/run", response_model=dict)
async def run_recommendations(
    user_id: int = Depends(get_current_user_id),
    engine: RecommendationEngine = Depends(_get_engine),
) -> Dict[str, Any]:
    try:
        result = engine.run_for_user(user_id)
    except Exception as exc:
        msg = str(exc).strip() if str(exc).strip() else "Recommendation run failed. Ensure migrations (003) are applied."
        logger.exception("Recommendations run failed for user_id=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=msg)
    return result


@router.get("/recommendations/latest", response_model=dict)
async def latest_recommendations(
    user_id: int = Depends(get_current_user_id),
    rec_svc: RecommendationDataService = Depends(_get_rec_data_service),
) -> Dict[str, Any]:
    run = rec_svc.get_latest_run(user_id)
    if not run:
        return {"run": None, "items": []}
    items = rec_svc.list_items_for_run(run["run_id"])
    summary_items = [
        {
            "symbol": i["symbol"],
            "score": str(i["score"]),
            "confidence": str(i.get("confidence") or "0"),
        }
        for i in items
    ]
    return {"run": run, "items": summary_items}


@router.get("/recommendations/{run_id}/explain", response_model=dict)
async def explain_recommendations(
    run_id: str,
    rec_svc: RecommendationDataService = Depends(_get_rec_data_service),
) -> Dict[str, Any]:
    try:
        rid = UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    # We do not know the user here; explanation is by run_id only.
    items = rec_svc.list_items_for_run(rid)
    if not items:
        raise HTTPException(status_code=404, detail="Run not found or has no items")
    return {
        "run_id": run_id,
        "items": [
            {
                "symbol": i["symbol"],
                "score": str(i["score"]),
                "confidence": str(i.get("confidence") or "0"),
                "explanation": i.get("explanation_json") or {},
            }
            for i in items
        ],
    }

