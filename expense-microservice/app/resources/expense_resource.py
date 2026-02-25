from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException

from app.models.expenses import (
    BalanceHistoryItem,
    BalanceHistoryResponse,
    ExpenseCreate,
    ExpenseUpdate,
    ExpenseResponse,
    ExpenseListParams,
    SummaryResponse,
    SummaryItem,
)
from app.services.expense_data_service import ExpenseDataService
from framework.resources.base_resource import BaseResource

SCHEMA = "expenses_db"
TABLE = "expense"


def _row_to_response(row: Dict[str, Any]) -> ExpenseResponse:
    return ExpenseResponse(
        expense_id=row["expense_id"],
        user_id=row["user_id"],
        category_code=row["category_code"],
        category_name=row["category_name"],
        amount=row["amount"],
        date=row["date"],
        currency=row["currency"],
        budget_category_id=row.get("budget_category_id"),
        description=row.get("description"),
        balance_after=row.get("balance_after"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        source=row.get("source"),
        plaid_transaction_id=row.get("plaid_transaction_id"),
    )


class ExpenseResource(BaseResource):
    def __init__(self, config: Any):
        super().__init__(config)
        self.data_service: ExpenseDataService = None  # type: ignore

    def get_by_key(self, key: str) -> Any:
        try:
            expense_id = UUID(key)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expense id")
        return self.get_by_id(expense_id, 0)  # user_id required from caller

    def get_by_id(self, expense_id: UUID, user_id: int) -> ExpenseResponse:
        row = self.data_service.get_expense_by_id(expense_id, user_id)
        if not row or row.get("deleted_at"):
            raise HTTPException(status_code=404, detail="Expense not found")
        return _row_to_response(row)

    def create(
        self,
        user_id: int,
        payload: ExpenseCreate,
        source: Optional[str] = None,
        plaid_transaction_id: Optional[str] = None,
    ) -> ExpenseResponse:
        resolved = self.data_service.resolve_category(
            payload.category_code, payload.category
        )
        if not resolved:
            raise HTTPException(
                status_code=400,
                detail="Invalid category: provide category (name) or category_code",
            )
        category_code, category_name = resolved
        now = datetime.now(timezone.utc)
        data = {
            "user_id": user_id,
            "category_code": category_code,
            "category_name": category_name,
            "amount": payload.amount,
            "date": payload.date,
            "currency": payload.currency or "USD",
            "budget_category_id": payload.budget_category_id,
            "description": payload.description,
            "balance_after": None,
            "created_at": now,
            "updated_at": now,
        }
        if source is not None:
            data["source"] = source
        if plaid_transaction_id is not None:
            data["plaid_transaction_id"] = plaid_transaction_id
        conn = self.data_service.get_connection(autocommit=False)
        try:
            self.data_service.acquire_user_lock(conn, user_id)
            self.data_service._insert_expense_using_conn(conn, data)
            expense_id = data["expense_id"]
            date_val = payload.date.isoformat()
            created_at = data["created_at"]
            prev = self.data_service.get_previous_expense(
                user_id, date_val, created_at, expense_id, conn=conn
            )
            balance_before = Decimal("0")
            if prev and prev.get("balance_after") is not None:
                balance_before = prev["balance_after"]
            new_balance = balance_before + payload.amount
            self.data_service.update_expense_balance_after(
                conn, str(expense_id), user_id, new_balance
            )
            data["balance_after"] = new_balance
            self.data_service.recalc_balance_after(
                conn, user_id, date_val, created_at, str(expense_id), new_balance
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            conn.close()
        return _row_to_response(data)

    def list(
        self, user_id: int, params: ExpenseListParams
    ) -> Tuple[List[ExpenseResponse], int]:
        date_from = params.date_from.isoformat() if params.date_from else None
        date_to = params.date_to.isoformat() if params.date_to else None
        offset = (params.page - 1) * params.page_size
        category_code = params.category_code
        if category_code is None and params.category and params.category.strip():
            resolved = self.data_service.resolve_category(None, params.category.strip())
            if resolved:
                category_code = resolved[0]
        rows, total = self.data_service.list_expenses(
            user_id,
            date_from=date_from,
            date_to=date_to,
            category_code=category_code,
            min_amount=params.min_amount,
            max_amount=params.max_amount,
            limit=params.page_size,
            offset=offset,
        )
        return [_row_to_response(r) for r in rows], total

    def update(
        self, expense_id: UUID, user_id: int, payload: ExpenseUpdate
    ) -> ExpenseResponse:
        existing = self.data_service.get_expense_by_id(expense_id, user_id)
        if not existing or existing.get("deleted_at"):
            raise HTTPException(status_code=404, detail="Expense not found")
        updates = {}
        if payload.amount is not None:
            updates["amount"] = payload.amount
        if payload.date is not None:
            updates["date"] = payload.date
        if payload.currency is not None:
            updates["currency"] = payload.currency
        if payload.budget_category_id is not None:
            updates["budget_category_id"] = payload.budget_category_id
        if payload.description is not None:
            updates["description"] = payload.description
        if payload.category_code is not None or payload.category is not None:
            resolved = self.data_service.resolve_category(
                payload.category_code, payload.category
            )
            if not resolved:
                raise HTTPException(status_code=400, detail="Invalid category")
            updates["category_code"], updates["category_name"] = resolved
        updates["updated_at"] = datetime.now(timezone.utc)
        if not updates:
            return _row_to_response(existing)
        conn = self.data_service.get_connection(autocommit=False)
        try:
            self.data_service.acquire_user_lock(conn, user_id)
            cur = conn.cursor()
            sets = ", ".join(f'"{k}" = %s' for k in updates)
            vals = list(updates.values()) + [str(expense_id), user_id]
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" SET {sets} WHERE expense_id = %s AND user_id = %s',
                vals,
            )
            if cur.rowcount == 0:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Expense not found")
            updated_row = self.data_service.get_expense_by_id(expense_id, user_id)
            pivot_date = updated_row["date"].isoformat() if hasattr(updated_row["date"], "isoformat") else str(updated_row["date"])
            pivot_created = updated_row["created_at"]
            pivot_id = str(expense_id)
            prev = self.data_service.get_previous_expense(
                user_id, pivot_date, pivot_created, expense_id, conn=conn
            )
            balance_before = Decimal("0")
            if prev and prev.get("balance_after") is not None:
                balance_before = prev["balance_after"]
            self.data_service.recalc_balance_after(
                conn, user_id, pivot_date, pivot_created, pivot_id, balance_before
            )
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            conn.close()
        row = self.data_service.get_expense_by_id(expense_id, user_id)
        return _row_to_response(row)

    def delete(self, expense_id: UUID, user_id: int) -> None:
        existing = self.data_service.get_expense_by_id(expense_id, user_id)
        if not existing or existing.get("deleted_at"):
            raise HTTPException(status_code=404, detail="Expense not found")
        conn = self.data_service.get_connection(autocommit=False)
        try:
            self.data_service.acquire_user_lock(conn, user_id)
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" SET deleted_at = %s, updated_at = %s '
                "WHERE expense_id = %s AND user_id = %s",
                (datetime.now(timezone.utc), datetime.now(timezone.utc), str(expense_id), user_id),
            )
            if cur.rowcount == 0:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Expense not found")
            date_val = existing["date"].isoformat() if hasattr(existing["date"], "isoformat") else str(existing["date"])
            created_at = existing["created_at"]
            prev = self.data_service.get_previous_expense(
                user_id, date_val, created_at, expense_id, conn=conn
            )
            balance_before = Decimal("0")
            if prev and prev.get("balance_after") is not None:
                balance_before = prev["balance_after"]
            self.data_service.recalc_balance_after(
                conn, user_id, date_val, created_at, str(expense_id), balance_before
            )
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            conn.close()

    def get_current_balance(
        self, user_id: int, as_of_date: Optional[str] = None
    ) -> Decimal:
        return self.data_service.get_current_balance(user_id, as_of_date)

    def get_balance_history(
        self,
        user_id: int,
        date_from: str,
        date_to: str,
        group_by: str = "week",
    ) -> BalanceHistoryResponse:
        rows = self.data_service.get_balance_history(
            user_id, date_from, date_to, group_by
        )
        items = [
            BalanceHistoryItem(date=r["date"], balance=r["balance"])
            for r in rows
        ]
        return BalanceHistoryResponse(items=items)

    def get_summary(
        self,
        user_id: int,
        group_by: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> SummaryResponse:
        if group_by not in ("category", "month"):
            raise HTTPException(status_code=400, detail="group_by must be 'category' or 'month'")
        rows = self.data_service.get_expense_summary(user_id, group_by, date_from, date_to)
        items = [SummaryItem(group_key=r["group_key"], label=r["label"], total_amount=r["total_amount"], count=r["count"]) for r in rows]
        return SummaryResponse(group_by=group_by, items=items)
