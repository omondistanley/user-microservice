"""Phase 4: Savings goals API."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user_id
from app.models.goals import GoalCreate, GoalResponse, GoalUpdate, ContributionCreate, ContributionResponse, GoalProgressResponse
from app.services.goal_data_service import GoalDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["goals"])


def _get_goal_service() -> GoalDataService:
    svc = ServiceFactory.get_service("GoalDataService")
    if not isinstance(svc, GoalDataService):
        raise RuntimeError("GoalDataService not available")
    return svc


def _row_to_goal(row: dict) -> GoalResponse:
    return GoalResponse(
        goal_id=row["goal_id"],
        user_id=row["user_id"],
        household_id=row.get("household_id"),
        name=row["name"],
        target_amount=row["target_amount"],
        target_currency=row["target_currency"],
        target_date=row.get("target_date"),
        start_amount=row["start_amount"],
        is_active=row["is_active"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("/goals", response_model=GoalResponse)
async def create_goal(
    payload: GoalCreate,
    user_id: int = Depends(get_current_user_id),
):
    svc = _get_goal_service()
    data = {
        "user_id": user_id,
        "name": payload.name,
        "target_amount": payload.target_amount,
        "target_currency": payload.target_currency,
        "target_date": payload.target_date,
        "start_amount": payload.start_amount,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    if payload.household_id is not None:
        data["household_id"] = str(payload.household_id)
    row = svc.create_goal(data)
    return _row_to_goal(row)


@router.get("/goals", response_model=dict)
async def list_goals(
    user_id: int = Depends(get_current_user_id),
    household_id: Optional[str] = Query(None),
    active_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    hh = None
    if household_id:
        try:
            UUID(household_id)
            hh = household_id
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid household_id")
    svc = _get_goal_service()
    offset = (page - 1) * page_size
    rows, total = svc.list_goals(user_id, household_id=hh, active_only=active_only, limit=page_size, offset=offset)
    return {"items": [_row_to_goal(r) for r in rows], "total": total}


@router.get("/goals/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        gid = UUID(goal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid goal_id")
    svc = _get_goal_service()
    row = svc.get_goal_by_id(gid, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Goal not found")
    return _row_to_goal(row)


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: str,
    payload: GoalUpdate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        gid = UUID(goal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid goal_id")
    svc = _get_goal_service()
    data = payload.model_dump(exclude_unset=True)
    row = svc.update_goal(gid, user_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="Goal not found")
    return _row_to_goal(row)


@router.delete("/goals/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        gid = UUID(goal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid goal_id")
    svc = _get_goal_service()
    if not svc.delete_goal(gid, user_id):
        raise HTTPException(status_code=404, detail="Goal not found")


@router.post("/goals/{goal_id}/contributions", response_model=ContributionResponse)
async def add_contribution(
    goal_id: str,
    payload: ContributionCreate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        gid = UUID(goal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid goal_id")
    svc = _get_goal_service()
    goal = svc.get_goal_by_id(gid, user_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    row = svc.add_contribution(gid, user_id, payload.amount, payload.contribution_date, payload.source)
    return ContributionResponse(
        contribution_id=row["contribution_id"],
        goal_id=row["goal_id"],
        user_id=row["user_id"],
        amount=row["amount"],
        contribution_date=row["contribution_date"],
        source=row["source"],
        created_at=row["created_at"],
    )


@router.get("/goals/{goal_id}/progress", response_model=GoalProgressResponse)
async def get_goal_progress(
    goal_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        gid = UUID(goal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid goal_id")
    svc = _get_goal_service()
    progress = svc.get_progress(gid, user_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Goal not found")
    return GoalProgressResponse(**progress)
