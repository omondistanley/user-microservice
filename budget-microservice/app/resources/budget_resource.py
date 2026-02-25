from datetime import date, datetime, timezone
from typing import Any, Dict, List, Tuple
from uuid import UUID

from fastapi import HTTPException

from app.models.budgets import (
    CATEGORY_NAMES,
    DEFAULT_END_DATE,
    BudgetCreate,
    BudgetUpdate,
    BudgetResponse,
    BudgetListParams,
)
from app.services.budget_data_service import BudgetDataService
from framework.resources.base_resource import BaseResource

VALID_CATEGORY_CODES = set(CATEGORY_NAMES.keys())


def _row_to_response(row: Dict[str, Any]) -> BudgetResponse:
    return BudgetResponse(
        budget_id=row["budget_id"],
        user_id=row["user_id"],
        name=row.get("name"),
        category_code=row["category_code"],
        category_name=CATEGORY_NAMES.get(row["category_code"], "Other"),
        amount=row["amount"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class BudgetResource(BaseResource):
    def __init__(self, config: Any):
        super().__init__(config)
        self.data_service: BudgetDataService = None  # type: ignore

    def get_by_key(self, key: str) -> BudgetResponse:
        """Required by BaseResource; API routes use get_by_id(budget_id, user_id) instead."""
        try:
            bid = UUID(key)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid budget id")
        return self.get_by_id(bid, 0)

    def get_by_id(self, budget_id: UUID, user_id: int) -> BudgetResponse:
        row = self.data_service.get_budget_by_id(budget_id, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="Budget not found")
        return _row_to_response(row)

    def create(self, user_id: int, payload: BudgetCreate) -> BudgetResponse:
        if payload.category_code not in VALID_CATEGORY_CODES:
            raise HTTPException(
                status_code=400,
                detail=f"category_code must be 1-8 (got {payload.category_code})",
            )
        end_date = payload.end_date if payload.end_date is not None else DEFAULT_END_DATE
        if payload.start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must be <= end_date",
            )
        now = datetime.now(timezone.utc)
        data = {
            "user_id": user_id,
            "name": payload.name,
            "category_code": payload.category_code,
            "amount": payload.amount,
            "start_date": payload.start_date,
            "end_date": end_date,
            "created_at": now,
            "updated_at": now,
        }
        inserted = self.data_service.insert_budget(data)
        return _row_to_response(inserted)

    def list(
        self, user_id: int, params: BudgetListParams
    ) -> Tuple[List[BudgetResponse], int]:
        effective_str = (
            params.effective_date.isoformat() if params.effective_date else None
        )
        rows, total = self.data_service.list_budgets(
            user_id=user_id,
            category_code=params.category_code,
            effective_date=effective_str,
            include_inactive=params.include_inactive,
            page=params.page,
            page_size=params.page_size,
        )
        return [_row_to_response(r) for r in rows], total

    def get_effective(
        self, user_id: int, category_code: int, effective_date: date
    ) -> BudgetResponse:
        if category_code not in VALID_CATEGORY_CODES:
            raise HTTPException(
                status_code=400,
                detail=f"category_code must be 1-8 (got {category_code})",
            )
        date_str = effective_date.isoformat()
        row = self.data_service.get_effective_budget(
            user_id, category_code, date_str
        )
        if not row:
            raise HTTPException(
                status_code=404,
                detail="No budget found for this category and date",
            )
        return _row_to_response(row)

    def update(
        self, budget_id: UUID, user_id: int, payload: BudgetUpdate
    ) -> BudgetResponse:
        existing = self.data_service.get_budget_by_id(budget_id, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Budget not found")

        # If only name is being updated, do simple update
        amount_or_dates = any(
            getattr(payload, f) is not None
            for f in ("amount", "start_date", "end_date")
        )
        if not amount_or_dates:
            if payload.name is not None:
                updated = self.data_service.update_budget(
                    budget_id, user_id, {"name": payload.name}
                )
                if updated:
                    return _row_to_response(updated)
            return _row_to_response(existing)

        # History: end current period and insert new row
        from datetime import timedelta

        new_start = payload.start_date if payload.start_date is not None else existing["start_date"]
        new_end = payload.end_date if payload.end_date is not None else existing["end_date"]
        new_amount = payload.amount if payload.amount is not None else existing["amount"]
        period_end = new_start - timedelta(days=1)

        self.data_service.end_budget_period(budget_id, user_id, period_end)
        now = datetime.now(timezone.utc)
        new_data = {
            "user_id": user_id,
            "name": payload.name if payload.name is not None else existing.get("name"),
            "category_code": existing["category_code"],
            "amount": new_amount,
            "start_date": new_start,
            "end_date": new_end,
            "created_at": now,
            "updated_at": now,
        }
        inserted = self.data_service.insert_budget(new_data)
        return _row_to_response(inserted)

    def delete(self, budget_id: UUID, user_id: int) -> None:
        existing = self.data_service.get_budget_by_id(budget_id, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Budget not found")
        if not self.data_service.delete_budget(budget_id, user_id):
            raise HTTPException(status_code=404, detail="Budget not found")
