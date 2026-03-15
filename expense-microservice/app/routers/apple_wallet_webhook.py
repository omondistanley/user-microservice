"""
Apple Wallet (Shortcuts) webhook: accept transaction payloads from iOS Shortcuts automation.
Creates expenses with source=apple_wallet and optional apple_wallet_transaction_id for idempotency.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import (
    APPLE_WALLET_WEBHOOK_SECRET,
    APPLE_WALLET_WEBHOOK_USER_ID,
)
from app.models.expenses import ExpenseCreate
from app.resources.expense_resource import ExpenseResource
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1/apple-wallet", tags=["apple-wallet"])


class AppleWalletWebhookPayload(BaseModel):
    merchant: str = Field(..., min_length=1, max_length=2000)
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD", max_length=8)
    date: str = Field(...)
    transaction_id: Optional[str] = Field(default=None, max_length=64)
    user_token: Optional[str] = Field(default=None, max_length=255)


def _get_expense_data_service() -> ExpenseDataService:
    svc = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(svc, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return svc


def _get_expense_resource() -> ExpenseResource:
    res = ServiceFactory.get_service("ExpenseResource")
    if not isinstance(res, ExpenseResource):
        raise RuntimeError("ExpenseResource not available")
    return res


def _resolve_user_id(user_token: Optional[str]) -> Optional[int]:
    """Resolve user_id: single-user from env, or from user_token (multi-user not implemented)."""
    if user_token:
        # Multi-user: could look up user_id from token table; not implemented for MVP
        return None
    if APPLE_WALLET_WEBHOOK_USER_ID:
        try:
            return int(APPLE_WALLET_WEBHOOK_USER_ID.strip())
        except ValueError:
            return None
    return None


@router.post("/webhook")
async def apple_wallet_webhook(
    body: AppleWalletWebhookPayload,
    x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
):
    """
    Receive a transaction from an iOS Shortcuts automation (e.g. triggered by Apple Pay).
    Requires X-Webhook-Secret header if APPLE_WALLET_WEBHOOK_SECRET is set.
    Single-user: set APPLE_WALLET_WEBHOOK_USER_ID. Optional body: transaction_id (idempotency), user_token (future).
    """
    if APPLE_WALLET_WEBHOOK_SECRET and x_webhook_secret != APPLE_WALLET_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")

    try:
        tx_date = date.fromisoformat(body.date.strip()[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date; use YYYY-MM-DD")

    user_id = _resolve_user_id(body.user_token)
    if user_id is None:
        if body.user_token:
            raise HTTPException(status_code=400, detail="Unknown user_token or multi-user not configured")
        raise HTTPException(
            status_code=503,
            detail="Apple Wallet webhook not configured: set APPLE_WALLET_WEBHOOK_USER_ID for single-user",
        )

    eds = _get_expense_data_service()
    resource = _get_expense_resource()

    if body.transaction_id:
        existing = eds.get_expense_by_apple_wallet_transaction_id(user_id, body.transaction_id)
        if existing:
            return {"status": "already_recorded", "expense_id": str(existing["expense_id"])}

    amount = Decimal(str(body.amount))
    description = (body.merchant or "Apple Wallet")[:2000]
    payload = ExpenseCreate(
        amount=amount,
        date=tx_date,
        category_code=8,
        currency=(body.currency or "USD").upper(),
        description=description,
    )
    created = resource.create(
        user_id,
        payload,
        source="apple_wallet",
        apple_wallet_transaction_id=body.transaction_id,
    )
    return {"status": "created", "expense_id": str(created.expense_id)}
