from datetime import date as date_type
from datetime import datetime, timedelta, timezone
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
        alert_configs=row.get("alert_configs") or [],
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
        row["alert_configs"] = self.data_service.get_budget_alert_configs(user_id, budget_id)
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
        if payload.household_id is not None:
            data["household_id"] = str(payload.household_id)
        inserted = self.data_service.insert_budget(data)
        if payload.alert_thresholds is not None:
            inserted["alert_configs"] = self.data_service.replace_budget_alert_configs(
                user_id=user_id,
                budget_id=inserted["budget_id"],
                thresholds=payload.alert_thresholds,
                channel=payload.alert_channel or "in_app",
            )
        else:
            inserted["alert_configs"] = []
        return _row_to_response(inserted)

    def list(
        self, user_id: int, params: BudgetListParams
    ) -> Tuple[List[BudgetResponse], int]:
        effective_str = (
            params.effective_date.isoformat() if params.effective_date else None
        )
        household_id = str(params.household_id) if params.household_id else None
        rows, total = self.data_service.list_budgets(
            user_id=user_id,
            category_code=params.category_code,
            effective_date=effective_str,
            include_inactive=params.include_inactive,
            household_id=household_id,
            page=params.page,
            page_size=params.page_size,
        )
        for row in rows:
            row["alert_configs"] = self.data_service.get_budget_alert_configs(
                user_id=user_id,
                budget_id=row["budget_id"],
            )
        return [_row_to_response(r) for r in rows], total

    def get_effective(
        self, user_id: int, category_code: int, effective_date: date_type
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
        row["alert_configs"] = self.data_service.get_budget_alert_configs(user_id, row["budget_id"])
        return _row_to_response(row)

    def update(
        self, budget_id: UUID, user_id: int, payload: BudgetUpdate
    ) -> BudgetResponse:
        existing = self.data_service.get_budget_by_id(budget_id, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Budget not found")
        existing_alert_configs = self.data_service.get_budget_alert_configs(user_id, budget_id)

        # If only name is being updated, do simple update
        amount_or_dates = any(
            getattr(payload, f) is not None
            for f in ("amount", "start_date", "end_date")
        )

        def _coerce_date(val: Any) -> date_type | None:
            if val is None:
                return None
            if isinstance(val, date_type):
                return val
            s = str(val)[:10]
            try:
                return date_type.fromisoformat(s)
            except ValueError:
                return None

        es = _coerce_date(existing["start_date"])
        ee = _coerce_date(existing["end_date"])
        ns = _coerce_date(payload.start_date) if payload.start_date is not None else es
        ne = _coerce_date(payload.end_date) if payload.end_date is not None else ee
        same_period = (
            es is not None
            and ee is not None
            and ns is not None
            and ne is not None
            and ns == es
            and ne == ee
        )

        # Same effective period: update amount/name/alerts in place (avoid period_end = start-1 bug).
        if amount_or_dates and same_period:
            updated_row = existing
            patch: Dict[str, Any] = {}
            if payload.name is not None:
                patch["name"] = payload.name
            if payload.amount is not None:
                patch["amount"] = payload.amount
            if patch:
                maybe_updated = self.data_service.update_budget(budget_id, user_id, patch)
                if maybe_updated:
                    updated_row = maybe_updated
            if payload.alert_thresholds is not None or payload.alert_channel is not None:
                thresholds = (
                    payload.alert_thresholds
                    if payload.alert_thresholds is not None
                    else [cfg["threshold_percent"] for cfg in existing_alert_configs]
                )
                channel = (
                    payload.alert_channel
                    or (existing_alert_configs[0]["channel"] if existing_alert_configs else "in_app")
                )
                updated_row["alert_configs"] = self.data_service.replace_budget_alert_configs(
                    user_id=user_id,
                    budget_id=budget_id,
                    thresholds=thresholds,
                    channel=channel,
                )
            else:
                updated_row["alert_configs"] = existing_alert_configs
            return _row_to_response(updated_row)

        if not amount_or_dates:
            updated_row = existing
            if payload.name is not None:
                maybe_updated = self.data_service.update_budget(
                    budget_id, user_id, {"name": payload.name}
                )
                if maybe_updated:
                    updated_row = maybe_updated
            if payload.alert_thresholds is not None or payload.alert_channel is not None:
                thresholds = (
                    payload.alert_thresholds
                    if payload.alert_thresholds is not None
                    else [cfg["threshold_percent"] for cfg in existing_alert_configs]
                )
                channel = (
                    payload.alert_channel
                    or (existing_alert_configs[0]["channel"] if existing_alert_configs else "in_app")
                )
                updated_row["alert_configs"] = self.data_service.replace_budget_alert_configs(
                    user_id=user_id,
                    budget_id=budget_id,
                    thresholds=thresholds,
                    channel=channel,
                )
            else:
                updated_row["alert_configs"] = existing_alert_configs
            return _row_to_response(updated_row)

        # History: end current period and insert new row
        new_start = payload.start_date if payload.start_date is not None else existing["start_date"]
        new_end = payload.end_date if payload.end_date is not None else existing["end_date"]
        new_amount = payload.amount if payload.amount is not None else existing["amount"]
        period_end = new_start - timedelta(days=1)

        alert_thresholds = payload.alert_thresholds
        if alert_thresholds is None:
            alert_thresholds = [cfg["threshold_percent"] for cfg in existing_alert_configs]
        alert_channel = (
            payload.alert_channel
            or (existing_alert_configs[0]["channel"] if existing_alert_configs else "in_app")
        )

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
        inserted["alert_configs"] = self.data_service.replace_budget_alert_configs(
            user_id=user_id,
            budget_id=inserted["budget_id"],
            thresholds=alert_thresholds,
            channel=alert_channel,
        )
        return _row_to_response(inserted)

    def delete(self, budget_id: UUID, user_id: int) -> None:
        existing = self.data_service.get_budget_by_id(budget_id, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Budget not found")
        if not self.data_service.delete_budget(budget_id, user_id):
            raise HTTPException(status_code=404, detail="Budget not found")
