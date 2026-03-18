"""
Plaid: link token, exchange, list/delete items, sync transactions to expenses.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
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
    create_hosted_link_session,
    exchange_public_token,
    fetch_transactions,
    is_configured,
    item_get,
    link_token_get,
)
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1/plaid", tags=["plaid"])


class PlaidItemExchangeBody(BaseModel):
    public_token: str


class PlaidSyncBody(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class PlaidHostedLinkBody(BaseModel):
    completion_redirect_uri: Optional[str] = None


class PlaidLinkTokenGetBody(BaseModel):
    link_token: str


def _get_plaid_data_service() -> PlaidDataService:
    svc = ServiceFactory.get_service("PlaidDataService")
    if svc is None:
        raise RuntimeError("PlaidDataService not available")
    return svc


def _get_expense_resource():
    return ServiceFactory.get_service("ExpenseResource")


def _get_expense_data_service():
    return ServiceFactory.get_service("ExpenseDataService")


@router.get("/status")
async def plaid_status():
    """Return whether Plaid is configured (for frontend to show fallback when not)."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="Plaid is not configured")
    return {"configured": True}


@router.post("/link-token")
async def plaid_link_token(user_id: int = Depends(get_current_user_id)):
    """Return a link_token for initializing Plaid Link."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="Plaid is not configured")
    link_token = create_link_token(user_id)
    if not link_token:
        raise HTTPException(status_code=503, detail="Failed to create link token")
    return {"link_token": link_token}


@router.post("/link-hosted")
async def plaid_link_hosted(
    body: Optional[PlaidHostedLinkBody] = None,
    user_id: int = Depends(get_current_user_id),
):
    """
    Create a Plaid Hosted Link session and return the hosted URL + link_token.
    The client should redirect the browser to hosted_link_url.

    After the user completes the flow, obtain public_token via webhook (preferred) or
    by calling /api/v1/plaid/link-token/get with the returned link_token (fallback).
    """
    if not is_configured():
        raise HTTPException(status_code=503, detail="Plaid is not configured")
    body = body or PlaidHostedLinkBody()
    session = create_hosted_link_session(
        user_id=user_id,
        completion_redirect_uri=body.completion_redirect_uri,
    )
    if not session:
        raise HTTPException(status_code=503, detail="Failed to create hosted link session")
    # Store link_token -> user mapping for webhook correlation.
    try:
        pds = _get_plaid_data_service()
        pds.save_link_token(user_id=user_id, link_token=session.get("link_token") or "", expiration_iso=session.get("expiration"))
    except Exception:
        pass
    return session


@router.post("/link-token/get")
async def plaid_link_token_get(
    body: PlaidLinkTokenGetBody,
    user_id: int = Depends(get_current_user_id),
):
    """
    Fallback path for Hosted Link: query Plaid for session completion + public_token.
    Returns { status, public_tokens, link_sessions? }.
    """
    if not is_configured():
        raise HTTPException(status_code=503, detail="Plaid is not configured")
    token = (body.link_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="link_token required")
    data = link_token_get(token)
    if not data:
        raise HTTPException(status_code=502, detail="Failed to get link token status")
    # Return a stable subset for frontend polling
    link_sessions = data.get("link_sessions") or []
    public_tokens: list[str] = []
    # Try new-style results first
    try:
        for s in link_sessions:
            res = (s or {}).get("results") or {}
            pts = res.get("public_tokens") or []
            if isinstance(pts, list):
                public_tokens.extend([str(x) for x in pts if x])
            on_success = (s or {}).get("on_success") or {}
            res2 = (on_success or {}).get("results") or {}
            pts2 = res2.get("public_tokens") or []
            if isinstance(pts2, list):
                public_tokens.extend([str(x) for x in pts2 if x])
    except Exception:
        pass
    # De-dup
    public_tokens = list(dict.fromkeys([p for p in public_tokens if p]))
    return {
        "link_token": token,
        "public_tokens": public_tokens,
        "link_sessions": link_sessions,
        "request_id": data.get("request_id"),
    }


@router.post("/webhook")
async def plaid_webhook(request: Request):
    """
    Dedicated Plaid webhook receiver for Hosted Link (SESSION_FINISHED).
    Expects the Plaid LINK webhook payload; when SUCCESS, exchanges public_token(s) and stores item(s).
    """
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return {"status": "ignored"}

    if (body.get("webhook_type") or "").upper() != "LINK":
        return {"status": "ignored"}
    if (body.get("webhook_code") or "").upper() != "SESSION_FINISHED":
        return {"status": "ignored"}
    if (body.get("status") or "").upper() != "SUCCESS":
        return {"status": "ignored", "reason": "not_success"}

    link_token = (body.get("link_token") or "").strip()
    public_tokens = body.get("public_tokens") or body.get("public_token") or []
    if isinstance(public_tokens, str):
        public_tokens = [public_tokens]
    if not link_token or not isinstance(public_tokens, list) or not public_tokens:
        return {"status": "ignored", "reason": "missing_tokens"}

    pds = _get_plaid_data_service()
    user_id = pds.get_user_id_for_link_token(link_token)
    if not user_id:
        # We may not have stored the link_token (older sessions); still accept.
        return {"status": "accepted", "linked": 0, "reason": "unknown_link_token"}

    linked = 0
    errors: list[str] = []
    for pt in public_tokens:
        pt = (str(pt) or "").strip()
        if not pt:
            continue
        try:
            result = exchange_public_token(pt)
            if not result:
                errors.append("exchange_failed")
                continue
            access_token = result.get("access_token")
            item_id = result.get("item_id")
            if not access_token or not item_id:
                errors.append("exchange_invalid")
                continue
            item_info = item_get(access_token)
            institution_id = item_info.get("institution_id") if item_info else None
            institution_name = (item_info.get("institution_name") or "Linked account") if item_info else "Linked account"
            encrypted = encrypt_access_token(access_token)
            if not encrypted:
                errors.append("encryption_not_configured")
                continue
            pds.save_plaid_item(
                user_id=user_id,
                item_id=item_id,
                access_token_encrypted=encrypted,
                institution_id=institution_id,
                institution_name=institution_name,
            )
            linked += 1
        except Exception as e:
            errors.append(str(e))
    return {"status": "accepted", "linked": linked, "errors": errors[:5]}


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
