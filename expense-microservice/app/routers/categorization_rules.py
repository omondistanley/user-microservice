"""CRUD for user categorization rules."""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user_id
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["categorization-rules"])

CONDITION_TYPES = {"merchant_contains", "category_is", "amount_above", "amount_below"}


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


@router.get("/categorization-rules", response_model=dict)
async def list_rules(
    user_id: int = Depends(get_current_user_id),
):
    """List all rules for the current user, ordered by priority."""
    ds = _get_data_service()
    rules = ds.list_rules_for_user(user_id)
    return {"rules": rules}


@router.post("/categorization-rules", response_model=dict)
async def create_rule(
    payload: dict,
    user_id: int = Depends(get_current_user_id),
):
    """
    Create a rule. Body: priority (int), condition_type, condition_value (dict),
    set_category_code (optional), set_tag_names (optional list), notify_on_match (bool), is_active (bool).
    """
    ds = _get_data_service()
    cond_type = (payload.get("condition_type") or "").strip().lower()
    if cond_type not in CONDITION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"condition_type must be one of: {', '.join(sorted(CONDITION_TYPES))}",
        )
    data = {
        "priority": int(payload.get("priority", 100)),
        "condition_type": cond_type,
        "condition_value": payload.get("condition_value") if isinstance(payload.get("condition_value"), dict) else {},
        "set_category_code": payload.get("set_category_code"),
        "set_tag_names": payload.get("set_tag_names") if isinstance(payload.get("set_tag_names"), list) else None,
        "notify_on_match": bool(payload.get("notify_on_match", False)),
        "is_active": bool(payload.get("is_active", True)),
    }
    if data["set_category_code"] is not None:
        try:
            data["set_category_code"] = int(data["set_category_code"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="set_category_code must be an integer")
    row = ds.create_rule(user_id, data)
    return row


@router.get("/categorization-rules/{rule_id}", response_model=dict)
async def get_rule(
    rule_id: str,
    user_id: int = Depends(get_current_user_id),
):
    ds = _get_data_service()
    rule = ds.get_rule_by_id(rule_id, user_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.patch("/categorization-rules/{rule_id}", response_model=dict)
async def update_rule(
    rule_id: str,
    payload: dict,
    user_id: int = Depends(get_current_user_id),
):
    ds = _get_data_service()
    ct = payload.get("condition_type")
    if ct is not None:
        ct_str = (ct.strip().lower() if isinstance(ct, str) else str(ct).strip().lower())
        if ct_str not in CONDITION_TYPES:
            raise HTTPException(status_code=400, detail=f"condition_type must be one of: {', '.join(sorted(CONDITION_TYPES))}")
    rule = ds.update_rule(rule_id, user_id, payload)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.delete("/categorization-rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    user_id: int = Depends(get_current_user_id),
):
    ds = _get_data_service()
    if not ds.delete_rule(rule_id, user_id):
        raise HTTPException(status_code=404, detail="Rule not found")
