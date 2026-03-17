"""
Rule engine: evaluate user categorization rules on expense create/update and apply category/tags.
"""
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx

from app.core.config import INTERNAL_API_KEY, USER_SERVICE_INTERNAL_URL
from app.services.expense_data_service import ExpenseDataService

logger = logging.getLogger(__name__)


def _evaluate_condition(
    rule: Dict[str, Any],
    description: Optional[str],
    amount: Optional[Decimal],
    category_code: Optional[int],
) -> bool:
    cond_type = (rule.get("condition_type") or "").strip().lower()
    cond_val = rule.get("condition_value") or {}
    if not isinstance(cond_val, dict):
        return False
    if cond_type == "merchant_contains":
        sub = (cond_val.get("substring") or cond_val.get("merchant") or "").strip()
        if not sub or description is None:
            return False
        return sub.lower() in (description or "").lower()
    if cond_type == "category_is":
        code = cond_val.get("category_code")
        if code is None:
            return False
        try:
            return int(category_code or 0) == int(code)
        except (TypeError, ValueError):
            return False
    if cond_type == "amount_above":
        try:
            threshold = Decimal(str(cond_val.get("amount", 0)))
        except Exception:
            return False
        return (amount or Decimal(0)) > threshold
    if cond_type == "amount_below":
        try:
            threshold = Decimal(str(cond_val.get("amount", 0)))
        except Exception:
            return False
        return (amount or Decimal(0)) < threshold
    return False


def _send_rule_notification(user_id: int, title: str, body: str, payload: Dict[str, Any]) -> None:
    if not USER_SERVICE_INTERNAL_URL:
        return
    headers = {"Content-Type": "application/json"}
    if INTERNAL_API_KEY:
        headers["x-internal-api-key"] = INTERNAL_API_KEY
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(
                f"{USER_SERVICE_INTERNAL_URL}/internal/v1/notifications",
                json={
                    "user_id": user_id,
                    "type": "rule_applied",
                    "title": title,
                    "body": body,
                    "payload": payload,
                },
                headers=headers,
            )
    except Exception as e:
        logger.warning("rule_engine notify failed: %s", e)


def evaluate_rules(
    ds: ExpenseDataService,
    user_id: int,
    expense_id: str,
    description: Optional[str],
    amount: Optional[Decimal],
    category_code: Optional[int],
    date_val: Any,
    source: Optional[str],
) -> Optional[str]:
    """
    Load active rules for user, evaluate in priority order; on first match apply category/tags
    and optionally notify. Returns applied rule_id or None.
    """
    rules = ds.list_active_rules_for_user(user_id)
    if not rules:
        return None
    for rule in rules:
        if not _evaluate_condition(rule, description, amount, category_code):
            continue
        rule_id = str(rule.get("rule_id") or "")
        set_code = rule.get("set_category_code")
        set_tags = rule.get("set_tag_names")
        if set_code is None and (not set_tags or not set_tags):
            continue
        updates = {}
        if set_code is not None:
            resolved = ds.resolve_category(set_code, None)
            if resolved:
                updates["category_code"], updates["category_name"] = resolved[0], resolved[1]
        if updates:
            try:
                ds.update_expense(UUID(expense_id), user_id, updates)
            except Exception as e:
                logger.warning("rule_engine update_expense failed: %s", e)
        if set_tags and set_tags:
            conn = ds.get_connection(autocommit=False)
            try:
                ds.set_expense_tags(conn, user_id, expense_id, tag_names=set_tags)
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.warning("rule_engine set_expense_tags failed: %s", e)
            finally:
                conn.close()
        if rule.get("notify_on_match"):
            _send_rule_notification(
                user_id,
                "Rule applied",
                f"Rule matched and updated expense {expense_id[:8]}...",
                {"rule_id": rule_id, "expense_id": expense_id},
            )
        return rule_id
    return None
