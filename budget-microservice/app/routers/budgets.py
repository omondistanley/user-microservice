from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.dependencies import get_current_user_id
from app.jobs.budget_alert_processor import evaluate_budget_alerts
from app.models.budgets import BudgetCreate, BudgetListParams, BudgetResponse, BudgetUpdate
from app.resources.budget_resource import BudgetResource
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["budgets"])


def _get_budget_resource() -> BudgetResource:
    res = ServiceFactory.get_service("BudgetResource")
    if res is None:
        raise RuntimeError("BudgetResource not available")
    return res


@router.get("/budgets", response_model=dict)
async def list_budgets(
    user_id: int = Depends(get_current_user_id),
    category_code: Optional[int] = Query(None, ge=1, le=8),
    effective_date: Optional[date] = Query(None),
    include_inactive: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    resource = _get_budget_resource()
    params = BudgetListParams(
        category_code=category_code,
        effective_date=effective_date,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )
    items, total = resource.list(user_id, params)
    return {"items": items, "total": total}


@router.get("/budgets/effective", response_model=BudgetResponse)
async def get_effective_budget(
    user_id: int = Depends(get_current_user_id),
    category_code: int = Query(..., ge=1, le=8),
    effective_date: date = Query(..., alias="date"),
):
    resource = _get_budget_resource()
    return resource.get_effective(user_id, category_code, effective_date)


@router.post("/budgets", response_model=BudgetResponse)
async def create_budget(
    payload: BudgetCreate,
    user_id: int = Depends(get_current_user_id),
):
    resource = _get_budget_resource()
    return resource.create(user_id, payload)


@router.get("/budgets/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        bid = UUID(budget_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid budget id")
    resource = _get_budget_resource()
    return resource.get_by_id(bid, user_id)


@router.patch("/budgets/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: str,
    payload: BudgetUpdate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        bid = UUID(budget_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid budget id")
    resource = _get_budget_resource()
    return resource.update(bid, user_id, payload)


@router.delete("/budgets/{budget_id}", status_code=204)
async def delete_budget(
    budget_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        bid = UUID(budget_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid budget id")
    resource = _get_budget_resource()
    resource.delete(bid, user_id)


@router.post("/budgets/alerts/evaluate", response_model=dict)
async def evaluate_alerts(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    as_of: Optional[date] = Query(None),
):
    request_id = str(getattr(request.state, "request_id", "") or "")
    result = evaluate_budget_alerts(
        as_of_date=as_of or date.today(),
        user_id=user_id,
        request_id=request_id or None,
    )
    return result
