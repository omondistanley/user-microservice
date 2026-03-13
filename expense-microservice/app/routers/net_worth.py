"""Net worth components derived from expense-domain cash and liabilities."""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user_id
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1/net-worth", tags=["net-worth"])


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


@router.get("/components")
async def net_worth_components(
    user_id: int = Depends(get_current_user_id),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    """Expense-domain balance sheet components.

    - assets.cash: current cash ledger balance
    - liabilities.spending_obligation: placeholder derived from expenses in window
      (until dedicated debt tables are introduced)
    """
    ds = _get_data_service()
    date_from_str = date_from.isoformat() if date_from else None
    date_to_str = date_to.isoformat() if date_to else None

    cash_balance = ds.get_current_balance(user_id=user_id, as_of_date=date_to_str)
    expense_total = ds.get_expense_total(
        user_id=user_id,
        date_from=date_from_str,
        date_to=date_to_str,
    )
    income_total = ds.get_income_total(
        user_id=user_id,
        date_from=date_from_str,
        date_to=date_to_str,
    )

    liabilities = expense_total if expense_total > Decimal("0") else Decimal("0")
    return {
        "assets": {
            "cash": cash_balance,
            "income_window_total": income_total,
        },
        "liabilities": {
            "spending_obligation": liabilities,
        },
        "metadata": {
            "as_of_date": date_to_str or date.today().isoformat(),
            "source": "expense_microservice",
            "notes": "spending_obligation is a placeholder until debt accounts are modeled",
        },
    }

