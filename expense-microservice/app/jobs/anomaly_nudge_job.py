"""
Anomaly nudge job: for users with recent expenses, detect anomalies and create
in-app notifications (skip if user already gave feedback). Limit per user per run.
"""
import logging
from typing import Any, Dict, List

import httpx

from app.core.config import INTERNAL_API_KEY, USER_SERVICE_INTERNAL_URL
from app.services.expense_data_service import ExpenseDataService
from app.services.insights_service import InsightsService
from app.services.service_factory import ServiceFactory

logger = logging.getLogger(__name__)

MAX_ANOMALY_NOTIFICATIONS_PER_USER = 5


def _notify_anomaly(user_id: int, anomaly: Dict[str, Any]) -> None:
    if not USER_SERVICE_INTERNAL_URL:
        return
    headers = {"Content-Type": "application/json"}
    if INTERNAL_API_KEY:
        headers["x-internal-api-key"] = INTERNAL_API_KEY
    payload = {
        "user_id": user_id,
        "type": "anomaly",
        "title": "Unusual spending",
        "body": anomaly.get("detail", "Unusual expense detected."),
        "payload": {
            "expense_id": anomaly.get("expense_id"),
            "amount": anomaly.get("amount"),
            "category_name": anomaly.get("category_name"),
            "date": anomaly.get("date"),
            "reason": anomaly.get("reason"),
        },
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(f"{USER_SERVICE_INTERNAL_URL}/internal/v1/notifications", json=payload, headers=headers)
    except Exception as e:
        logger.warning("anomaly_nudge notify failed: %s", e)


def run_anomaly_nudge_job(job_id: str = "", limit_per_user: int = MAX_ANOMALY_NOTIFICATIONS_PER_USER) -> Dict[str, Any]:
    """
    For each user with recent expenses: detect anomalies, then for each (up to limit_per_user)
    skip if feedback exists, else create notification.
    """
    expense_ds = ServiceFactory.get_service("ExpenseDataService")
    insights_svc = ServiceFactory.get_service("InsightsService")
    if not isinstance(expense_ds, ExpenseDataService) or not isinstance(insights_svc, InsightsService):
        return {"error": "services not available", "processed": 0}
    user_ids = expense_ds.get_user_ids_with_recent_expenses(days=7)
    sent_total = 0
    for user_id in user_ids:
        try:
            anomalies = insights_svc.detect_anomalies(user_id, limit=100)
            sent = 0
            for a in anomalies:
                if sent >= limit_per_user:
                    break
                expense_id = a.get("expense_id")
                if not expense_id:
                    continue
                if insights_svc.has_anomaly_feedback(user_id, expense_id):
                    continue
                _notify_anomaly(user_id, a)
                sent += 1
            sent_total += sent
        except Exception as e:
            logger.exception("anomaly_nudge user_id=%s error: %s", user_id, e)
    return {"processed_users": len(user_ids), "notifications_sent": sent_total, "job_id": job_id}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    result = run_anomaly_nudge_job("cli")
    print(result)
    sys.exit(0)
