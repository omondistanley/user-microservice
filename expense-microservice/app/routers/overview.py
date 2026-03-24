"""Aggregated overview: sync status + analytics KPIs for dashboards."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user_id
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["overview"])


def _ds() -> ExpenseDataService:
    svc = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(svc, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return svc


@router.get("/sync-status", response_model=dict)
async def sync_status(user_id: int = Depends(get_current_user_id)):
    return _ds().get_user_sync_summary(user_id)


@router.get("/analytics/overview", response_model=dict)
async def analytics_overview(
    user_id: int = Depends(get_current_user_id),
    days: int = Query(30, ge=7, le=366),
):
    """
    KPIs for analytics screen: trailing spend/income totals and category breakdown.
    """
    ds = _ds()
    end = date.today()
    start = end - timedelta(days=days - 1)
    df = start.isoformat()
    dt = end.isoformat()
    income_total = ds.get_income_total(user_id=user_id, date_from=df, date_to=dt)
    expense_total = ds.get_expense_total(user_id=user_id, date_from=df, date_to=dt)
    by_cat = ds.get_expense_summary(user_id=user_id, group_by="category", date_from=df, date_to=dt)
    return {
        "period": {"date_from": df, "date_to": dt, "days": days},
        "income_total": str(income_total),
        "expense_total": str(expense_total),
        "net": str(income_total - expense_total),
        "spend_by_category": [
            {
                "category_code": row.get("group_key"),
                "label": row.get("label"),
                "total": str(row.get("total_amount") or 0),
                "count": row.get("count"),
            }
            for row in (by_cat or [])
        ],
    }
