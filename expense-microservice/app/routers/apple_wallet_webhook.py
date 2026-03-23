"""
Apple Wallet (Shortcuts) webhook: accept transaction payloads from iOS Shortcuts automation.
Creates expenses with source=apple_wallet and optional apple_wallet_transaction_id for idempotency.

Personal Automation flow (no Finance Toolkit required):
  - iOS Shortcut fires on "Wallet" notification (Personal Automation trigger)
  - Extracts merchant + amount from notification body, generates a UUID transaction_id
  - POSTs to POST /api/v1/apple-wallet/webhook
  - GET  /api/v1/apple-wallet/last-sync  → when was the last delta fetch?
  - GET  /api/v1/apple-wallet/since-last-sync → returns all new records + advances cursor
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

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
from app.services.transaction_classifier import classify_transaction

router = APIRouter(prefix="/api/v1/apple-wallet", tags=["apple-wallet"])


class AppleWalletWebhookPayload(BaseModel):
    merchant: str = Field(..., min_length=1, max_length=2000)
    amount: float = Field(...)
    currency: str = Field(default="USD", max_length=8)
    date: str = Field(...)
    time: Optional[str] = Field(default=None, max_length=8)
    timestamp: Optional[str] = Field(default=None, max_length=64)
    note: Optional[str] = Field(default=None, max_length=2000)
    flow_type: Optional[str] = Field(default=None, max_length=16)
    category_hint: Optional[str] = Field(default=None, max_length=64)
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

    amount = Decimal(str(body.amount))
    if amount == 0:
        raise HTTPException(status_code=400, detail="amount must be non-zero")

    classification = classify_transaction(
        amount=amount,
        merchant=body.merchant,
        note=body.note,
        flow_type_hint=body.flow_type,
    )
    amount_abs = abs(amount)

    if body.transaction_id:
        existing_expense = eds.get_expense_by_apple_wallet_transaction_id(user_id, body.transaction_id)
        if existing_expense:
            return {
                "status": "already_recorded",
                "flow_type": "expense",
                "category_hint": classification.category_hint if classification.flow_type == "expense" else "expense_other",
                "expense_id": str(existing_expense["expense_id"]),
            }
        existing_income = eds.get_income_by_apple_wallet_transaction_id(user_id, body.transaction_id)
        if existing_income:
            return {
                "status": "already_recorded",
                "flow_type": "income",
                "category_hint": "income_salary_other",
                "income_type": str(existing_income.get("income_type") or "other"),
                "income_id": str(existing_income["income_id"]),
            }

    description_parts = [body.merchant.strip()]
    if body.note:
        description_parts.append(body.note.strip())
    if body.time:
        description_parts.append(f"time={body.time.strip()}")
    if body.timestamp:
        description_parts.append(f"timestamp={body.timestamp.strip()}")
    description = " | ".join([p for p in description_parts if p])[:2000]

    if classification.flow_type == "income":
        now = datetime.now(timezone.utc)
        income_row = eds.create_income(
            {
                "user_id": user_id,
                "amount": amount_abs,
                "date": tx_date,
                "currency": (body.currency or "USD").upper(),
                "income_type": classification.income_type or "other",
                "source_label": (body.merchant or "Apple Wallet")[:255],
                "description": description,
                "apple_wallet_transaction_id": body.transaction_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        eds.update_apple_wallet_last_sync(user_id, now)
        return {
            "status": "created",
            "flow_type": "income",
            "category_hint": classification.category_hint,
            "income_type": classification.income_type or "other",
            "income_id": str(income_row.get("income_id")),
        }

    payload = ExpenseCreate(
        amount=amount_abs,
        date=tx_date,
        category_code=classification.category_code or 8,
        currency=(body.currency or "USD").upper(),
        description=description,
    )
    created = resource.create(
        user_id,
        payload,
        source="apple_wallet",
        apple_wallet_transaction_id=body.transaction_id,
    )
    eds.update_apple_wallet_last_sync(user_id, datetime.now(timezone.utc))
    return {
        "status": "created",
        "flow_type": "expense",
        "category_hint": classification.category_hint,
        "expense_id": str(created.expense_id),
    }


@router.get("/last-sync")
async def apple_wallet_last_sync(
    x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
):
    """
    Returns the timestamp of the last successful /since-last-sync call.
    iOS Shortcut can poll this to show when data was last fetched.
    """
    if APPLE_WALLET_WEBHOOK_SECRET and x_webhook_secret != APPLE_WALLET_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")

    user_id = _resolve_user_id(None)
    if user_id is None:
        raise HTTPException(status_code=503, detail="Apple Wallet not configured")

    eds = _get_expense_data_service()
    last_sync = eds.get_apple_wallet_last_sync(user_id)
    return {
        "last_sync_at": last_sync.isoformat() if last_sync else None,
        "user_id": user_id,
    }


@router.get("/since-last-sync")
async def apple_wallet_since_last_sync(
    x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
):
    """
    Returns all Apple Wallet expenses and income created since the last time this
    endpoint was called. Advances the sync cursor atomically after fetching.

    iOS Personal Automation Shortcut calls this after every Apple Pay tap (or on a
    schedule) to get a delta of new transactions and display a summary notification.

    Response shape:
      {
        "since": "<ISO timestamp or null>",
        "synced_at": "<ISO timestamp>",
        "expenses": [...],
        "income": [...],
        "totals": { "expense": <float>, "income": <float>, "net": <float> }
      }
    """
    if APPLE_WALLET_WEBHOOK_SECRET and x_webhook_secret != APPLE_WALLET_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")

    user_id = _resolve_user_id(None)
    if user_id is None:
        raise HTTPException(status_code=503, detail="Apple Wallet not configured")

    eds = _get_expense_data_service()

    # Snapshot the previous cursor BEFORE fetching so the window is consistent
    last_sync = eds.get_apple_wallet_last_sync(user_id)

    expenses: List[dict] = eds.get_expenses_since(user_id, since=last_sync)
    income: List[dict] = eds.get_income_since(user_id, since=last_sync)

    # Advance cursor to now
    synced_at = datetime.now(timezone.utc)
    eds.update_apple_wallet_last_sync(user_id, synced_at)

    total_expense = float(sum(Decimal(str(e.get("amount", 0))) for e in expenses))
    total_income = float(sum(Decimal(str(i.get("amount", 0))) for i in income))

    # Serialise UUIDs / dates for JSON
    def _serialise(rows: List[dict]) -> List[dict]:
        out = []
        for row in rows:
            out.append({k: str(v) if not isinstance(v, (int, float, bool, type(None))) else v
                        for k, v in row.items()})
        return out

    return {
        "since": last_sync.isoformat() if last_sync else None,
        "synced_at": synced_at.isoformat(),
        "expenses": _serialise(expenses),
        "income": _serialise(income),
        "totals": {
            "expense": total_expense,
            "income": total_income,
            "net": round(total_income - total_expense, 2),
        },
    }
