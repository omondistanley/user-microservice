from typing import Any, List, Tuple
from uuid import UUID

from fastapi import HTTPException

from app.models.holdings import HoldingCreate, HoldingListParams, HoldingResponse, HoldingUpdate
from app.services.holdings_data_service import HoldingsDataService
from framework.resources.base_resource import BaseResource


def _row_to_response(row: dict) -> HoldingResponse:
    return HoldingResponse(
        holding_id=row["holding_id"],
        user_id=row["user_id"],
        household_id=row.get("household_id"),
        symbol=row["symbol"],
        quantity=row["quantity"],
        avg_cost=row["avg_cost"],
        currency=row["currency"],
        exchange=row.get("exchange"),
        notes=row.get("notes"),
        source=row.get("source"),
        external_id=row.get("external_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class HoldingResource(BaseResource):
    def __init__(self, config: Any):
        super().__init__(config)
        self.data_service: HoldingsDataService = None  # type: ignore

    def get_by_key(self, key: str) -> HoldingResponse:
        try:
            hid = UUID(key)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid holding id")
        return self.get_by_id(hid, 0)

    def get_by_id(self, holding_id: UUID, user_id: int) -> HoldingResponse:
        row = self.data_service.get_holding_by_id(holding_id, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="Holding not found")
        return _row_to_response(row)

    def create(self, user_id: int, payload: HoldingCreate) -> HoldingResponse:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        data = {
            "user_id": user_id,
            "symbol": payload.symbol.upper().strip(),
            "quantity": payload.quantity,
            "avg_cost": payload.avg_cost,
            "currency": payload.currency.upper(),
            "exchange": payload.exchange,
            "notes": payload.notes,
            "created_at": now,
            "updated_at": now,
        }
        if payload.household_id is not None:
            data["household_id"] = str(payload.household_id)
        inserted = self.data_service.insert_holding(data)
        return _row_to_response(inserted)

    def list(
        self, user_id: int, params: HoldingListParams
    ) -> Tuple[List[HoldingResponse], int]:
        items, total = self.data_service.list_holdings(
            user_id=user_id,
            household_id=params.household_id,
            symbol=params.symbol,
            page=params.page,
            page_size=params.page_size,
        )
        return [_row_to_response(r) for r in items], total

    def update(self, holding_id: UUID, user_id: int, payload: HoldingUpdate) -> HoldingResponse:
        updates = payload.model_dump(exclude_unset=True)
        row = self.data_service.update_holding(holding_id, user_id, updates)
        if not row:
            raise HTTPException(status_code=404, detail="Holding not found")
        return _row_to_response(row)

    def delete(self, holding_id: UUID, user_id: int) -> None:
        if not self.data_service.delete_holding(holding_id, user_id):
            raise HTTPException(status_code=404, detail="Holding not found")
