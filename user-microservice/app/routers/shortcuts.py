"""
iOS Shortcuts integration — lightweight transaction ingestion endpoint.
POST /api/v1/shortcuts/transaction

Accepts a simple JSON body so an iOS Shortcut can log an expense in one tap
without opening the app. Uses the same JWT auth as every other endpoint.

Body (all optional except amount):
    {
        "amount":      123.45,           # required, positive number
        "description": "Coffee",         # optional free-text
        "category":    "food",           # optional category hint
        "date":        "2026-04-05"      # optional ISO date, defaults to today
    }

Returns 201 with { "id": <expense_id>, "message": "Logged." }
"""
import logging
from datetime import date, datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user
from app.core.config import EXPENSE_SERVICE_URL

logger = logging.getLogger(__name__)
router = APIRouter()


class ShortcutTransactionRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Transaction amount, positive")
    description: Optional[str] = Field(None, max_length=255)
    category: Optional[str] = Field(None, max_length=64)
    date: Optional[str] = Field(None, description="ISO date YYYY-MM-DD, defaults to today")


@router.post("/api/v1/shortcuts/transaction", tags=["shortcuts"], status_code=201)
async def shortcuts_log_transaction(
    payload: ShortcutTransactionRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    iOS Shortcuts quick-add expense endpoint.
    Proxies a POST to the expense microservice on behalf of the authenticated user.
    """
    txn_date = payload.date or date.today().isoformat()
    try:
        datetime.strptime(txn_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD format.")

    body = {
        "amount": payload.amount,
        "description": payload.description or "Quick expense",
        "category_name": payload.category or "Other",
        "date": txn_date,
        "source": "ios_shortcut",
    }

    token = current_user.get("_raw_token", "")
    base = (EXPENSE_SERVICE_URL or "").rstrip("/")
    url = f"{base}/api/v1/expenses"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        if resp.status_code not in (200, 201):
            detail = resp.text[:300] if resp.text else "Upstream error"
            raise HTTPException(status_code=resp.status_code, detail=detail)
        data = resp.json()
        return {"id": data.get("id") or data.get("expense_id"), "message": "Logged."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("iOS Shortcuts proxy failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to forward to expense service.")
