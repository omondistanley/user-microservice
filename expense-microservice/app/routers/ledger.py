"""Unified expense + income ledger (transactions)."""
from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user_id
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["transactions"])


def _ds() -> ExpenseDataService:
    svc = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(svc, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return svc


@router.get("/transactions", response_model=dict)
async def list_transactions(
    user_id: int = Depends(get_current_user_id),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    entry_type: Optional[Literal["expense", "income"]] = Query(None),
    category_code: Optional[int] = Query(None, ge=1, le=8),
    income_type: Optional[str] = Query(None),
    tag_id: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    min_amount: Optional[Decimal] = Query(None),
    max_amount: Optional[Decimal] = Query(None),
    household_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if tag_id:
        try:
            UUID(tag_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tag id")
    hh = None
    if household_id:
        try:
            UUID(household_id)
            hh = household_id
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid household_id")
    ds = _ds()
    items, total = ds.list_unified_ledger(
        user_id=user_id,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        entry_type=entry_type,
        category_code=category_code,
        income_type_filter=income_type,
        tag_id=tag_id,
        tag_slug=tag,
        search=search,
        min_amount=min_amount,
        max_amount=max_amount,
        household_id=hh,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
