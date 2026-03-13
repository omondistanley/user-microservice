"""Unified bank connector API across providers."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.adapters.truelayer_adapter import TrueLayerAdapter, is_configured as truelayer_configured
from app.core.dependencies import get_current_user_id
from app.routers.plaid import PlaidSyncBody, plaid_sync
from app.routers.teller import TellerSyncBody, teller_sync
from app.services.plaid_data_service import PlaidDataService, encrypt_access_token as encrypt_plaid_token
from app.services.plaid_service import (
    create_link_token as plaid_create_link_token,
    exchange_public_token as plaid_exchange_public_token,
    is_configured as plaid_configured,
    item_get as plaid_item_get,
)
from app.services.service_factory import ServiceFactory
from app.services.teller_data_service import TellerDataService, encrypt_access_token as encrypt_teller_token
from app.services.teller_service import is_configured as teller_configured

router = APIRouter(prefix="/api/v1/bank", tags=["bank"])


class BankLinkSessionBody(BaseModel):
    provider: Literal["plaid", "teller", "truelayer"]


class BankExchangeTokenBody(BaseModel):
    provider: Literal["plaid", "teller", "truelayer"]
    public_token: Optional[str] = None
    code: Optional[str] = None
    access_token: Optional[str] = None
    enrollment_id: Optional[str] = None
    institution_name: Optional[str] = None


class BankSyncBody(BaseModel):
    provider: Literal["plaid", "teller"]
    date_from: Optional[str] = None
    date_to: Optional[str] = None


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


@router.get("/status")
async def bank_status():
    return {
        "providers": {
            "plaid": {"configured": bool(plaid_configured())},
            "teller": {"configured": bool(teller_configured())},
            "truelayer": {"configured": bool(truelayer_configured())},
        }
    }


@router.get("/items")
async def list_bank_items(user_id: int = Depends(get_current_user_id)):
    plaid_items = _get_plaid_data_service().get_plaid_items(user_id)
    teller_items = _get_teller_data_service().get_enrollments(user_id)
    return {
        "items": [
            {
                "provider": "plaid",
                "item_id": row["item_id"],
                "name": row.get("institution_name") or "Linked account",
                "created_at": row.get("created_at"),
            }
            for row in plaid_items
        ]
        + [
            {
                "provider": "teller",
                "item_id": row["enrollment_id"],
                "name": row.get("institution_name") or "Linked account",
                "created_at": row.get("created_at"),
            }
            for row in teller_items
        ]
    }


@router.post("/link-session")
async def create_bank_link_session(
    body: BankLinkSessionBody,
    user_id: int = Depends(get_current_user_id),
):
    if body.provider == "plaid":
        if not plaid_configured():
            raise HTTPException(status_code=503, detail="Plaid is not configured")
        token = plaid_create_link_token(user_id)
        if not token:
            raise HTTPException(status_code=503, detail="Failed to create Plaid link token")
        return {"provider": "plaid", "link_token": token}
    if body.provider == "teller":
        if not teller_configured():
            raise HTTPException(status_code=503, detail="Teller is not configured")
        from app.core.config import TELLER_APP_ID, TELLER_ENV

        return {"provider": "teller", "app_id": TELLER_APP_ID, "environment": TELLER_ENV or "sandbox"}
    if body.provider == "truelayer":
        if not truelayer_configured():
            raise HTTPException(status_code=503, detail="TrueLayer is not configured")
        link_url = TrueLayerAdapter().create_link_session(user_id)
        if not link_url:
            raise HTTPException(status_code=503, detail="TrueLayer link session not available")
        return {"provider": "truelayer", "link_url": link_url}
    raise HTTPException(status_code=400, detail="Unsupported provider")


@router.post("/exchange-token")
async def exchange_bank_token(
    body: BankExchangeTokenBody,
    user_id: int = Depends(get_current_user_id),
):
    if body.provider == "plaid":
        if not body.public_token:
            raise HTTPException(status_code=400, detail="public_token required")
        result = plaid_exchange_public_token(body.public_token)
        if not result:
            raise HTTPException(status_code=400, detail="Failed to exchange Plaid token")
        access_token = result.get("access_token")
        item_id = result.get("item_id")
        if not access_token or not item_id:
            raise HTTPException(status_code=400, detail="Invalid Plaid exchange response")
        item_info = plaid_item_get(access_token)
        institution_id = item_info.get("institution_id") if item_info else None
        institution_name = (item_info.get("institution_name") or "Linked account") if item_info else "Linked account"
        encrypted = encrypt_plaid_token(access_token)
        if not encrypted:
            raise HTTPException(status_code=500, detail="Encryption not configured")
        _get_plaid_data_service().save_plaid_item(
            user_id=user_id,
            item_id=item_id,
            access_token_encrypted=encrypted,
            institution_id=institution_id,
            institution_name=institution_name,
        )
        return {"provider": "plaid", "item_id": item_id, "institution_name": institution_name}

    if body.provider == "teller":
        if not body.access_token or not body.enrollment_id:
            raise HTTPException(status_code=400, detail="access_token and enrollment_id required")
        encrypted = encrypt_teller_token(body.access_token)
        if not encrypted:
            raise HTTPException(status_code=500, detail="Encryption not configured")
        _get_teller_data_service().save_enrollment(
            user_id=user_id,
            enrollment_id=body.enrollment_id,
            access_token_encrypted=encrypted,
            institution_name=body.institution_name,
        )
        return {
            "provider": "teller",
            "item_id": body.enrollment_id,
            "institution_name": body.institution_name or "Linked account",
        }

    if body.provider == "truelayer":
        if not body.code:
            raise HTTPException(status_code=400, detail="code required")
        result = TrueLayerAdapter().exchange_public_token(user_id, body.code)
        if not result:
            raise HTTPException(status_code=503, detail="TrueLayer exchange not implemented")
        return {"provider": "truelayer", **result}
    raise HTTPException(status_code=400, detail="Unsupported provider")


@router.post("/sync")
async def sync_bank_transactions(
    body: BankSyncBody,
    user_id: int = Depends(get_current_user_id),
):
    if body.provider == "plaid":
        return await plaid_sync(body=PlaidSyncBody(date_from=body.date_from, date_to=body.date_to), user_id=user_id)
    if body.provider == "teller":
        return await teller_sync(body=TellerSyncBody(date_from=body.date_from, date_to=body.date_to), user_id=user_id)
    raise HTTPException(status_code=400, detail="Unsupported provider")


@router.delete("/items/{provider}/{item_id}")
async def disconnect_bank_item(
    provider: Literal["plaid", "teller"],
    item_id: str,
    user_id: int = Depends(get_current_user_id),
):
    if provider == "plaid":
        ok = _get_plaid_data_service().delete_plaid_item(user_id, item_id)
    else:
        ok = _get_teller_data_service().delete_enrollment(user_id, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}
