import calendar
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user_id
from app.models.expenses import ExpenseCreate, ExpenseResponse
from app.models.recurring import (
    RecurrenceRule,
    RecurringExpenseCreate,
    RecurringExpenseResponse,
    RecurringExpenseUpdate,
)
from app.resources.expense_resource import ExpenseResource
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["recurring-expenses"])


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


def _get_expense_resource() -> ExpenseResource:
    resource = ServiceFactory.get_service("ExpenseResource")
    if not isinstance(resource, ExpenseResource):
        raise RuntimeError("ExpenseResource not available")
    return resource


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _advance_due_date(current_due: date, rule: RecurrenceRule) -> date:
    if rule == "weekly":
        return current_due.fromordinal(current_due.toordinal() + 7)
    if rule == "monthly":
        return _add_months(current_due, 1)
    return _add_months(current_due, 12)


@router.post("/recurring-expenses", response_model=RecurringExpenseResponse)
async def create_recurring_expense(
    payload: RecurringExpenseCreate,
    user_id: int = Depends(get_current_user_id),
):
    ds = _get_data_service()
    resolved = ds.resolve_category(payload.category_code, payload.category)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="Invalid category: provide category (name) or category_code",
        )
    category_code, category_name = resolved
    now = datetime.now(timezone.utc)
    row = ds.create_recurring_expense(
        {
            "user_id": user_id,
            "amount": payload.amount,
            "currency": (payload.currency or "USD").upper(),
            "category_code": category_code,
            "category_name": category_name,
            "description": payload.description,
            "recurrence_rule": payload.recurrence_rule,
            "next_due_date": payload.next_due_date,
            "is_active": payload.is_active,
            "created_at": now,
            "updated_at": now,
        }
    )
    return RecurringExpenseResponse(**row)


@router.get("/recurring-expenses", response_model=dict)
async def list_recurring_expenses(
    user_id: int = Depends(get_current_user_id),
    active_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    ds = _get_data_service()
    items, total = ds.list_recurring_expenses(
        user_id=user_id,
        active_only=active_only,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return {"items": [RecurringExpenseResponse(**r) for r in items], "total": total}


@router.get("/recurring-expenses/{recurring_id}", response_model=RecurringExpenseResponse)
async def get_recurring_expense(
    recurring_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        UUID(recurring_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recurring expense id")
    ds = _get_data_service()
    row = ds.get_recurring_expense_by_id(recurring_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    return RecurringExpenseResponse(**row)


@router.patch("/recurring-expenses/{recurring_id}", response_model=RecurringExpenseResponse)
async def update_recurring_expense(
    recurring_id: str,
    payload: RecurringExpenseUpdate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        UUID(recurring_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recurring expense id")
    ds = _get_data_service()
    updates = payload.model_dump(exclude_unset=True)
    if "category_code" in updates or "category" in updates:
        resolved = ds.resolve_category(updates.get("category_code"), updates.get("category"))
        if not resolved:
            raise HTTPException(status_code=400, detail="Invalid category")
        updates["category_code"], updates["category_name"] = resolved
    updates.pop("category", None)
    if "currency" in updates and updates["currency"]:
        updates["currency"] = str(updates["currency"]).upper()
    updates["updated_at"] = datetime.now(timezone.utc)
    row = ds.update_recurring_expense(recurring_id, user_id, updates)
    if not row:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    return RecurringExpenseResponse(**row)


@router.delete("/recurring-expenses/{recurring_id}", status_code=204)
async def delete_recurring_expense(
    recurring_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        UUID(recurring_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recurring expense id")
    ds = _get_data_service()
    if not ds.delete_recurring_expense(recurring_id, user_id):
        raise HTTPException(status_code=404, detail="Recurring expense not found")


@router.post("/recurring-expenses/{recurring_id}/run", response_model=dict)
async def run_recurring_expense(
    recurring_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        UUID(recurring_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recurring expense id")

    ds = _get_data_service()
    recurring = ds.get_recurring_expense_by_id(recurring_id, user_id)
    if not recurring:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    if not recurring.get("is_active", True):
        raise HTTPException(status_code=400, detail="Recurring expense is inactive")

    expense_resource = _get_expense_resource()
    due_date = recurring.get("next_due_date")
    if not isinstance(due_date, date):
        try:
            due_date = date.fromisoformat(str(due_date))
        except Exception:
            due_date = date.today()

    created_expense = expense_resource.create(
        user_id=user_id,
        payload=ExpenseCreate(
            amount=Decimal(str(recurring["amount"])),
            date=due_date,
            category_code=int(recurring["category_code"]),
            currency=str(recurring.get("currency") or "USD"),
            description=recurring.get("description"),
        ),
        source="recurring",
    )

    now = datetime.now(timezone.utc)
    next_due = _advance_due_date(due_date, recurring["recurrence_rule"])
    updated = ds.update_recurring_expense(
        recurring_id,
        user_id,
        {
            "last_run_at": now,
            "last_created_expense_id": str(created_expense.expense_id),
            "next_due_date": next_due,
            "updated_at": now,
        },
    )
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update recurring expense after run")

    return {
        "recurring": RecurringExpenseResponse(**updated),
        "created_expense": ExpenseResponse(**created_expense.model_dump()),
    }
