from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import INTERNAL_API_KEY
from app.routers.plaid import PlaidSyncBody, plaid_sync
from app.routers.teller import TellerSyncBody, teller_sync
from app.services.expense_data_service import ExpenseDataService
from app.services.plaid_data_service import PlaidDataService
from app.services.service_factory import ServiceFactory
from app.services.teller_data_service import TellerDataService

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def _validate_internal_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    if INTERNAL_API_KEY and x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


def _get_plaid_data_service() -> PlaidDataService:
    svc = ServiceFactory.get_service("PlaidDataService")
    if not isinstance(svc, PlaidDataService):
        raise RuntimeError("PlaidDataService not available")
    return svc


def _get_teller_data_service() -> TellerDataService:
    svc = ServiceFactory.get_service("TellerDataService")
    if not isinstance(svc, TellerDataService):
        raise RuntimeError("TellerDataService not available")
    return svc


class ProviderWebhookEvent(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    event_id: str = Field(..., min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)


def _pick_nested(payload: dict[str, Any], keys: list[str]) -> Optional[str]:
    for key in keys:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    data_obj = payload.get("data")
    if isinstance(data_obj, dict):
        for key in keys:
            val = data_obj.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


@router.delete("/users/{user_id}/expenses", response_model=dict, include_in_schema=False)
async def purge_user_expenses(
    user_id: int,
    request: Request,
    _: None = Depends(_validate_internal_key),
):
    ds = _get_data_service()
    result = ds.purge_user_data(user_id)
    request_id = str(getattr(request.state, "request_id", "") or "")
    return {
        "user_id": user_id,
        "request_id": request_id or None,
        "result": result,
    }


@router.post("/providers/webhook-event", include_in_schema=False)
async def process_provider_webhook_event(
    body: ProviderWebhookEvent,
    _: None = Depends(_validate_internal_key),
):
    provider = body.provider.strip().lower()
    payload = body.payload or {}

    if provider == "plaid":
        item_id = _pick_nested(payload, ["item_id", "itemId"])
        if not item_id:
            return {"ok": False, "provider": provider, "reason": "missing_item_id"}
        pds = _get_plaid_data_service()
        owner_user_id: Optional[int] = pds.get_plaid_item_owner(str(item_id))
        if owner_user_id is None:
            return {"ok": False, "provider": provider, "reason": "item_not_linked"}
        result = await plaid_sync(body=PlaidSyncBody(), user_id=owner_user_id)
        return {"ok": True, "provider": provider, "user_id": owner_user_id, "sync": result}

    if provider == "teller":
        enrollment_id = _pick_nested(payload, ["enrollment_id", "enrollmentId"])
        if not enrollment_id:
            return {"ok": False, "provider": provider, "reason": "missing_enrollment_id"}
        tds = _get_teller_data_service()
        owner_user_id = tds.get_enrollment_owner(str(enrollment_id))
        if owner_user_id is None:
            return {"ok": False, "provider": provider, "reason": "enrollment_not_linked"}
        result = await teller_sync(body=TellerSyncBody(), user_id=owner_user_id)
        return {"ok": True, "provider": provider, "user_id": owner_user_id, "sync": result}

    return {"ok": False, "provider": provider, "reason": "unsupported_provider"}
