"""
Teller: store enrollment (access_token), list/delete enrollments, sync transactions to expenses.
The frontend uses Teller Connect (JS widget) which returns an enrollment object with access_token.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_current_user_id
from app.models.expenses import ExpenseCreate
from app.services.teller_data_service import (
    TellerDataService,
    decrypt_access_token,
    encrypt_access_token,
)
from app.services.teller_service import (
    is_configured,
    list_accounts,
    list_transactions,
)
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1/teller", tags=["teller"])


class TellerEnrollBody(BaseModel):
    access_token: str
    enrollment_id: str
    institution_name: Optional[str] = None


class TellerSyncBody(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None


def _get_teller_data_service() -> TellerDataService:
    svc = ServiceFactory.get_service("TellerDataService")
    if svc is None:
        raise RuntimeError("TellerDataService not available")
    return svc


def _get_expense_resource():
    return ServiceFactory.get_service("ExpenseResource")


def _get_expense_data_service():
    return ServiceFactory.get_service("ExpenseDataService")


@router.get("/config")
async def teller_config():
    """Return Teller app_id for the frontend widget."""
    from app.core.config import TELLER_APP_ID, TELLER_ENV
    if not TELLER_APP_ID:
        raise HTTPException(status_code=503, detail="Teller is not configured")
    return {"app_id": TELLER_APP_ID, "environment": TELLER_ENV or "sandbox"}


@router.post("/enrollment")
async def teller_save_enrollment(
    body: TellerEnrollBody,
    user_id: int = Depends(get_current_user_id),
):
    """Save Teller enrollment returned by Teller Connect widget."""
    if not body.access_token or not body.enrollment_id:
        raise HTTPException(status_code=400, detail="access_token and enrollment_id required")
    encrypted = encrypt_access_token(body.access_token)
    if not encrypted:
        raise HTTPException(status_code=500, detail="Encryption not configured")
    tds = _get_teller_data_service()
    row = tds.save_enrollment(
        user_id=user_id,
        enrollment_id=body.enrollment_id,
        access_token_encrypted=encrypted,
        institution_name=body.institution_name,
    )
    # Fetch real accounts to get institution name if not provided
    institution_name = body.institution_name
    if not institution_name:
        accounts = list_accounts(body.access_token)
        if accounts:
            institution_name = (accounts[0].get("institution") or {}).get("name") or "Linked account"
            tds.save_enrollment(
                user_id=user_id,
                enrollment_id=body.enrollment_id,
                access_token_encrypted=encrypted,
                institution_name=institution_name,
            )
    return {
        "enrollment_id": body.enrollment_id,
        "institution_name": institution_name or "Linked account",
    }


@router.get("/enrollments")
async def teller_list_enrollments(user_id: int = Depends(get_current_user_id)):
    """List all linked Teller enrollments for the user."""
    tds = _get_teller_data_service()
    items = tds.get_enrollments(user_id)
    return {
        "items": [
            {
                "enrollment_id": i["enrollment_id"],
                "institution_name": i.get("institution_name") or "Linked account",
                "created_at": i["created_at"].isoformat() if hasattr(i.get("created_at"), "isoformat") else str(i.get("created_at")),
            }
            for i in items
        ]
    }


@router.delete("/enrollments/{enrollment_id}")
async def teller_delete_enrollment(
    enrollment_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """Remove a linked Teller enrollment."""
    tds = _get_teller_data_service()
    if not tds.delete_enrollment(user_id, enrollment_id):
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return {"ok": True}


def _teller_type_to_category_code(tx_type: Any, description: str) -> int:
    """Map Teller transaction type/description to our category_code. Default 8 = Other."""
    desc = (description or "").lower()
    tx_type = (tx_type or "").lower()
    if any(w in desc for w in ["restaurant", "food", "grocery", "cafe", "coffee", "pizza", "burger"]):
        return 1
    if any(w in desc for w in ["uber", "lyft", "gas", "fuel", "transport", "parking", "transit", "metro"]):
        return 2
    if any(w in desc for w in ["hotel", "airbnb", "flight", "airline", "travel"]):
        return 3
    if any(w in desc for w in ["electric", "water", "utility", "internet", "phone", "bill"]):
        return 4
    if any(w in desc for w in ["netflix", "spotify", "entertainment", "cinema", "theater", "hulu"]):
        return 5
    if any(w in desc for w in ["pharmacy", "doctor", "medical", "health", "hospital", "clinic"]):
        return 6
    if any(w in desc for w in ["amazon", "shop", "store", "target", "walmart", "mall"]):
        return 7
    return 8


@router.post("/sync")
async def teller_sync(
    body: Optional[TellerSyncBody] = None,
    user_id: int = Depends(get_current_user_id),
):
    """Fetch transactions from all linked Teller enrollments and create expenses."""
    body = body or TellerSyncBody()
    end = date.today()
    start = end - timedelta(days=30)
    if body.date_from:
        try:
            start = date.fromisoformat(body.date_from[:10])
        except ValueError:
            pass
    if body.date_to:
        try:
            end = date.fromisoformat(body.date_to[:10])
        except ValueError:
            pass

    tds = _get_teller_data_service()
    eds = _get_expense_data_service()
    resource = _get_expense_resource()
    enrollments = tds.get_enrollments(user_id)
    created = 0
    errors: List[str] = []

    for enrollment in enrollments:
        row = tds.get_enrollment_by_id(user_id, enrollment["enrollment_id"])
        if not row:
            continue
        access_token_enc = row.get("access_token_encrypted")
        if not access_token_enc:
            continue
        access_token = decrypt_access_token(access_token_enc)
        if not access_token:
            errors.append(f"Could not decrypt token for enrollment {enrollment['enrollment_id']}")
            continue

        accounts = list_accounts(access_token)
        for account in accounts:
            account_id = account.get("id")
            if not account_id:
                continue
            transactions = list_transactions(access_token, account_id)
            for tx in transactions:
                tx_id = tx.get("id")
                if not tx_id:
                    continue
                # Skip credits (income) — only sync debits as expenses
                # Note: "digital_wallet" is a Teller sub-type (not "credit"), so it falls through
                if tx.get("type") == "credit":
                    continue
                amount_raw = tx.get("amount")
                if amount_raw is None:
                    continue
                amount = abs(Decimal(str(amount_raw)))
                if amount == 0:
                    continue
                # Date filter
                tx_date_str = tx.get("date")
                if not tx_date_str:
                    continue
                try:
                    tx_date = date.fromisoformat(tx_date_str[:10])
                except ValueError:
                    continue
                if not (start <= tx_date <= end):
                    continue
                # Dedup check
                if eds.get_expense_by_teller_transaction_id(user_id, tx_id):
                    continue
                description = (tx.get("description") or tx.get("merchant") or {})
                if isinstance(description, dict):
                    description = description.get("name") or "Transaction"
                description = str(description).strip() or "Expense"
                tx_type = tx.get("type") or ""
                category_code = _teller_type_to_category_code(tx_type, description)
                # Detect digital wallet (Apple Pay / Google Pay via Teller)
                tx_source = "teller"
                if tx_type == "digital_wallet":
                    desc_upper = description.upper()
                    if "GOOGLE" in desc_upper or "GPAY" in desc_upper:
                        tx_source = "teller_google_pay"
                    else:
                        tx_source = "teller_apple_pay"
                payload = ExpenseCreate(
                    amount=amount,
                    date=tx_date,
                    category_code=category_code,
                    currency=(account.get("currency") or "USD").upper(),
                    description=description[:2000],
                )
                try:
                    resource.create(
                        user_id,
                        payload,
                        source=tx_source,
                        teller_transaction_id=tx_id,
                    )
                    created += 1
                except Exception as e:
                    errors.append(f"{tx_id}: {e}")

    return {"created": created, "errors": errors[:20]}
