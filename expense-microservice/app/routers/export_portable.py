"""Phase 7: Portable export (schema version + normalized JSON bundle)."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.dependencies import get_current_user_id
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["export"])
SCHEMA_VERSION = "1.0"


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


@router.get("/export/portable")
async def export_portable(
    user_id: int = Depends(get_current_user_id),
    format: str = Query("json", pattern="^json$"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    """Return normalized JSON bundle with schema version for round-trip/portability."""
    ds = _get_data_service()
    expenses = ds.list_expenses_for_export(
        user_id=user_id,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
    )
    income_rows, _ = ds.list_income(
        user_id,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        limit=10000,
        offset=0,
    )
    income = [dict(r) for r in income_rows]
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": date.today().isoformat(),
        "meta": {
            "user_id": user_id,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "round_trip_import": "/api/v1/import/portable",
            "supported_csv_presets": ["generic", "plaid", "teller"],
        },
        "expenses": expenses,
        "income": income,
    }
    return JSONResponse(content=jsonable_encoder(bundle))
