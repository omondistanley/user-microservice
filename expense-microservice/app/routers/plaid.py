"""
Plaid: link token, exchange, list/delete items, sync transactions to expenses.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_current_user_id
from app.models.expenses import ExpenseCreate
from app.services.plaid_data_service import (
    PlaidDataService,
    decrypt_access_token,
    encrypt_access_token,
)
from app.services.plaid_service import (
    create_link_token,
    exchange_public_token,
    fetch_transactions,
    is_configured,
    item_get,
)
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1/plaid", tags=["plaid"])


class PlaidItemExchangeBody(BaseModel):
    public_token: str


class PlaidSyncBody(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None


def _get_plaid_data_service() -> PlaidDataService:
    svc = ServiceFactory.get_service("PlaidDataService")
    if svc is None:
        raise RuntimeError("PlaidDataService not available")
    return svc


def _get_expense_resource():
    return ServiceFactory.get_service("ExpenseResource")


def _get_expense_data_service():
    return ServiceFactory.get_service("ExpenseDataService")


@router.post("/link-token")
async def plaid_link_token(user_id: int = Depends(get_current_user_id)):
    """Return a link_token for initializing Plaid Link."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="Plaid is not configured")
    link_token = create_link_token(user_id)
    if not link_token:
        raise HTTPException(status_code=503, detail="Failed to create link token")
    return {"link_token": link_token}


@router.post("/item")
async def plaid_exchange_item(
    body: PlaidItemExchangeBody,
    user_id: int = Depends(get_current_user_id),
):
    """Exchange public_token from Link; store item and return item_id, institution_name."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="Plaid is not configured")
    public_token = body.public_token
    if not public_token:
        raise HTTPException(status_code=400, detail="public_token required")
    result = exchange_public_token(public_token)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to exchange token")
    access_token = result.get("access_token")
    item_id = result.get("item_id")
    if not access_token or not item_id:
        raise HTTPException(status_code=400, detail="Invalid exchange response")
    item_info = item_get(access_token)
    institution_id = item_info.get("institution_id") if item_info else None
    institution_name = (item_info.get("institution_name") or "Linked account") if item_info else "Linked account"
    encrypted = encrypt_access_token(access_token)
    if not encrypted:
        raise HTTPException(status_code=500, detail="Encryption not configured")
    pds = _get_plaid_data_service()
    row = pds.save_plaid_item(
        user_id=user_id,
        item_id=item_id,
        access_token_encrypted=encrypted,
        institution_id=institution_id,
        institution_name=institution_name,
    )
    return {
        "item_id": item_id,
        "institution_name": institution_name or "Linked account",
    }


@router.get("/items")
async def plaid_list_items(user_id: int = Depends(get_current_user_id)):
    """List linked Plaid items (no access_token)."""
    pds = _get_plaid_data_service()
    items = pds.get_plaid_items(user_id)
    return {
        "items": [
            {
                "item_id": i["item_id"],
                "institution_id": i.get("institution_id"),
                "institution_name": i.get("institution_name") or "Linked account",
                "created_at": i["created_at"].isoformat() if hasattr(i.get("created_at"), "isoformat") else str(i.get("created_at")),
            }
            for i in items
        ]
    }


@router.delete("/items/{item_id}")
async def plaid_delete_item(
    item_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """Remove a linked Plaid item."""
    pds = _get_plaid_data_service()
    if not pds.delete_plaid_item(user_id, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"ok": True}


def _plaid_category_to_code(plaid_category: Any) -> int:
    """Map Plaid category to our category_code. Default 8 = Other."""
    if not plaid_category:
        return 8
    if isinstance(plaid_category, list):
        primary = (plaid_category or [""])[0] if plaid_category else ""
    else:
        primary = str(plaid_category)
    primary_lower = primary.lower()
    if "food" in primary_lower or "restaurant" in primary_lower or "grocer" in primary_lower:
        return 1
    if "transport" in primary_lower or "auto" in primary_lower or "gas" in primary_lower:
        return 2
    if "travel" in primary_lower or "airline" in primary_lower or "hotel" in primary_lower:
        return 3
    if "utility" in primary_lower or "utility" in primary_lower:
        return 4
    if "entertainment" in primary_lower or "recreation" in primary_lower:
        return 5
    if "health" in primary_lower or "medical" in primary_lower or "pharmacy" in primary_lower:
        return 6
    if "shop" in primary_lower or "merchandise" in primary_lower:
        return 7
    return 8


@router.post("/sync")
async def plaid_sync(
    body: Optional[PlaidSyncBody] = None,
    user_id: int = Depends(get_current_user_id),
):
    """Fetch transactions from all linked items and create expenses for new transactions."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="Plaid is not configured")
    body = body or PlaidSyncBody()
    date_from_str = body.date_from
    date_to_str = body.date_to
    end = date.today()
    start = end - timedelta(days=30)
    if date_from_str:
        try:
            start = date.fromisoformat(date_from_str[:10])
        except ValueError:
            pass
    if date_to_str:
        try:
            end = date.fromisoformat(date_to_str[:10])
        except ValueError:
            pass
    if start > end:
        start, end = end, start
    pds = _get_plaid_data_service()
    eds = _get_expense_data_service()
    resource = _get_expense_resource()
    items = pds.get_plaid_items(user_id)
    created = 0
    errors: List[str] = []
    for item in items:
        row = pds.get_plaid_item_by_item_id(user_id, item["item_id"])
        if not row:
            continue
        access_token_enc = row.get("access_token_encrypted")
        if not access_token_enc:
            continue
        access_token = decrypt_access_token(access_token_enc)
        if not access_token:
            errors.append(f"Could not decrypt token for item {item['item_id']}")
            continue
        transactions = fetch_transactions(access_token, start, end)
        for tx in transactions:
            if tx.get("pending"):
                continue
            tx_id = tx.get("transaction_id") or tx.get("id")
            if not tx_id:
                continue
            amount_raw = tx.get("amount")
            if amount_raw is None:
                continue
            amount = Decimal(str(amount_raw))
            if amount == 0:
                continue
            amount = abs(amount)
            if eds.get_expense_by_plaid_transaction_id(user_id, tx_id):
                continue
            tx_date_str = tx.get("date")
            if not tx_date_str:
                continue
            try:
                tx_date = date.fromisoformat(tx_date_str[:10])
            except ValueError:
                continue
            name = (tx.get("name") or tx.get("merchant_name") or "Transaction").strip() or "Expense"
            category_code = _plaid_category_to_code(tx.get("category") or tx.get("personal_finance_category"))
            payload = ExpenseCreate(
                amount=amount,
                date=tx_date,
                category_code=category_code,
                currency="USD",
                description=name[:2000] if len(name) > 2000 else name,
            )
            try:
                resource.create(
                    user_id,
                    payload,
                    source="plaid",
                    plaid_transaction_id=tx_id,
                )
                created += 1
            except Exception as e:
                errors.append(f"{tx_id}: {e}")
    return {"created": created, "errors": errors[:20]}
