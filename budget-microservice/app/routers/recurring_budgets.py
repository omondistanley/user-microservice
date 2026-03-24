from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user_id
from app.models.budgets import (
    CATEGORY_NAMES,
    RecurringBudgetCreate,
    RecurringBudgetResponse,
    RecurringBudgetUpdate,
)
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1/recurring-budgets", tags=["recurring-budgets"])


def _row_to_response(row: dict) -> RecurringBudgetResponse:
    return RecurringBudgetResponse(
        recurring_budget_id=row["recurring_budget_id"],
        user_id=row["user_id"],
        name=row.get("name"),
        category_code=row["category_code"],
        category_name=CATEGORY_NAMES.get(row["category_code"], "Other"),
        amount=row["amount"],
        cadence=row["cadence"],
        start_date=row["start_date"],
        next_period_start=row["next_period_start"],
        is_active=row["is_active"],
        household_id=row.get("household_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("", response_model=dict)
async def list_recurring_budgets(
    user_id: int = Depends(get_current_user_id),
    include_inactive: bool = Query(False),
    household_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    ds = ServiceFactory.get_service("BudgetDataService")
    hh = None
    if household_id:
        try:
            hh = str(UUID(household_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid household_id")
    rows, total = ds.list_recurring_budgets(
        user_id=user_id,
        include_inactive=include_inactive,
        household_id=hh,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [_row_to_response(r).model_dump(mode="json") for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", response_model=RecurringBudgetResponse)
async def create_recurring_budget(
    payload: RecurringBudgetCreate,
    user_id: int = Depends(get_current_user_id),
):
    ds = ServiceFactory.get_service("BudgetDataService")
    nps = payload.next_period_start or payload.start_date
    row = ds.insert_recurring_budget(
        {
            "user_id": user_id,
            "name": payload.name,
            "category_code": payload.category_code,
            "amount": payload.amount,
            "cadence": payload.cadence,
            "start_date": payload.start_date,
            "next_period_start": nps,
            "is_active": True,
            "household_id": str(payload.household_id) if payload.household_id else None,
        }
    )
    full = ds.get_recurring_budget(row["recurring_budget_id"], user_id)
    return _row_to_response(full or row)


@router.get("/{recurring_budget_id}", response_model=RecurringBudgetResponse)
async def get_recurring_budget(
    recurring_budget_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        rid = UUID(recurring_budget_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id")
    ds = ServiceFactory.get_service("BudgetDataService")
    row = ds.get_recurring_budget(rid, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return _row_to_response(row)


@router.patch("/{recurring_budget_id}", response_model=RecurringBudgetResponse)
async def patch_recurring_budget(
    recurring_budget_id: str,
    payload: RecurringBudgetUpdate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        rid = UUID(recurring_budget_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id")
    ds = ServiceFactory.get_service("BudgetDataService")
    data = payload.model_dump(exclude_unset=True)
    if "household_id" in data:
        data["household_id"] = str(data["household_id"]) if data["household_id"] else None
    row = ds.update_recurring_budget(rid, user_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return _row_to_response(row)


@router.delete("/{recurring_budget_id}", status_code=204)
async def delete_recurring_budget(
    recurring_budget_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        rid = UUID(recurring_budget_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id")
    ds = ServiceFactory.get_service("BudgetDataService")
    if not ds.delete_recurring_budget(rid, user_id):
        raise HTTPException(status_code=404, detail="Not found")
