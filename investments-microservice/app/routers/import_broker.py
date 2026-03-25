"""
Multi-broker CSV import endpoint.
Parses broker export files and bulk-creates holdings.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.dependencies import get_current_user_id
from app.services.broker_csv_parser import BrokerParseError, parse_broker_csv
from app.services.holdings_data_service import HoldingsDataService
from app.services.service_factory import ServiceFactory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["import"])


def _get_data_service() -> HoldingsDataService:
    ds = ServiceFactory.get_service("HoldingsDataService")
    if not isinstance(ds, HoldingsDataService):
        raise RuntimeError("HoldingsDataService not available")
    return ds


@router.post("/holdings/import-csv", response_model=dict)
async def import_broker_csv(
    file: UploadFile = File(...),
    broker: Optional[str] = Form(None),
    account_type: str = Form(default="taxable"),
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
):
    """
    Import holdings from a broker CSV export.
    Supported brokers: fidelity, schwab, vanguard, etoro, td (auto-detected if not specified).
    Deduplicates by (user_id, symbol) — updates existing holding if symbol already exists.
    Not financial advice. For informational purposes only.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")

    content = (await file.read()).decode("utf-8", errors="replace")
    try:
        detected_broker, holdings = parse_broker_csv(content, broker)
    except BrokerParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not holdings:
        raise HTTPException(status_code=422, detail="No valid holdings found in the CSV file.")

    created = 0
    updated = 0
    skipped = 0
    errors = []

    for h in holdings:
        try:
            from app.models.holdings import HoldingCreate
            payload = HoldingCreate(
                symbol=h["symbol"],
                quantity=h["quantity"],
                avg_cost=h["avg_cost"],
                currency=h.get("currency", "USD"),
                account_type=account_type,
            )
            from app.resources.holding_resource import HoldingResource
            resource = ServiceFactory.get_service("HoldingResource")
            result = resource.create(user_id, payload)
            created += 1
        except Exception as e:
            err_str = str(e).lower()
            if "duplicate" in err_str or "unique" in err_str:
                skipped += 1
            else:
                errors.append(f"{h['symbol']}: {e}")

    return {
        "broker": detected_broker,
        "total_rows": len(holdings),
        "created": created,
        "skipped_duplicates": skipped,
        "errors": errors[:10],
        "disclaimer": "Not financial advice. Imported holdings are for informational tracking only.",
    }
