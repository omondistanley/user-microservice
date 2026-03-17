"""
Low projected balance alert: if user's projected balance (current - recurring due in 30 days)
falls below their configured threshold, send one notification per day (deduped).
"""
import logging
from datetime import date, timedelta

import httpx

from app.core.config import INTERNAL_API_KEY, USER_SERVICE_INTERNAL_URL
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

logger = logging.getLogger(__name__)

PROJECTED_DAYS = 30


def _notify_low_projected_balance(user_id: int, projected_balance: float, threshold: float) -> None:
    if not USER_SERVICE_INTERNAL_URL:
        return
    headers = {"Content-Type": "application/json"}
    if INTERNAL_API_KEY:
        headers["x-internal-api-key"] = INTERNAL_API_KEY
    payload = {
        "user_id": user_id,
        "type": "low_projected_balance",
        "title": "Projected balance low",
        "body": f"Your projected balance in {PROJECTED_DAYS} days is below your threshold (${projected_balance:.2f} < ${threshold:.2f}). Consider adjusting spending or adding income.",
        "payload": {"projected_balance": projected_balance, "threshold": threshold, "days": PROJECTED_DAYS},
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(f"{USER_SERVICE_INTERNAL_URL}/internal/v1/notifications", json=payload, headers=headers)
    except Exception as e:
        logger.warning("low_projected_balance notify failed: %s", e)


def run_low_projected_balance_job(job_id: str = "") -> dict:
    """
    For each user with recent expenses and a low_projected_balance threshold set:
    compute projected balance (30 days); if below threshold, send at most one notification per day.
    """
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        return {"error": "ExpenseDataService not available", "sent": 0}
    today = date.today()
    end_date = today + timedelta(days=PROJECTED_DAYS)
    user_ids = ds.get_user_ids_with_recent_expenses(days=60)
    sent = 0
    for user_id in user_ids:
        try:
            pref = ds.get_alert_preference(user_id, "low_projected_balance")
            if not pref or pref.get("threshold_value") is None:
                continue
            threshold = float(pref["threshold_value"])
            current = ds.get_current_balance(user_id, today.isoformat())
            recurring_due = ds.get_recurring_total_due_in_range(
                user_id, today + timedelta(days=1), end_date
            )
            projected = float(current - recurring_due)
            if projected >= threshold:
                continue
            if ds.record_low_projected_balance_sent_if_new(user_id, today):
                _notify_low_projected_balance(user_id, projected, threshold)
                sent += 1
        except Exception as e:
            logger.exception("low_projected_balance user_id=%s error: %s", user_id, e)
    return {"sent": sent, "job_id": job_id}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    result = run_low_projected_balance_job("cli")
    print(result)
    sys.exit(0)
