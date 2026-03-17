"""
No-income nudge: if current month has no income logged and we're past the first week,
send one notification per user per month (deduped).
"""
import logging
from calendar import monthrange
from datetime import date

import httpx

from app.core.config import INTERNAL_API_KEY, USER_SERVICE_INTERNAL_URL
from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

logger = logging.getLogger(__name__)


def _notify_no_income(user_id: int, year_month: str) -> None:
    if not USER_SERVICE_INTERNAL_URL:
        return
    headers = {"Content-Type": "application/json"}
    if INTERNAL_API_KEY:
        headers["x-internal-api-key"] = INTERNAL_API_KEY
    payload = {
        "user_id": user_id,
        "type": "no_income_logged",
        "title": "No income logged this month",
        "body": f"You haven't logged any income for {year_month}. Add income to keep your cashflow and savings on track.",
        "payload": {"year_month": year_month},
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(f"{USER_SERVICE_INTERNAL_URL}/internal/v1/notifications", json=payload, headers=headers)
    except Exception as e:
        logger.warning("no_income_nudge notify failed: %s", e)


def run_no_income_nudge_job(job_id: str = "") -> dict:
    """
    For each user with recent expenses: if current month income is 0 and we're past day 7,
    send at most one no_income_logged notification per month (deduped).
    """
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        return {"error": "ExpenseDataService not available", "sent": 0}
    today = date.today()
    if today.day <= 7:
        return {"skipped": "before_day_7", "sent": 0, "job_id": job_id}
    year_month = today.strftime("%Y-%m")
    first_day = today.replace(day=1)
    _, last_day_num = monthrange(today.year, today.month)
    last_day = today.replace(day=last_day_num)
    date_from = first_day.isoformat()
    date_to = last_day.isoformat()
    user_ids = ds.get_user_ids_with_recent_expenses(days=60)
    sent = 0
    for user_id in user_ids:
        try:
            total = ds.get_income_total(user_id, date_from=date_from, date_to=date_to)
            if total and total != 0:
                continue
            if ds.record_no_income_sent_if_new(user_id, year_month):
                _notify_no_income(user_id, year_month)
                sent += 1
        except Exception as e:
            logger.exception("no_income_nudge user_id=%s error: %s", user_id, e)
    return {"sent": sent, "year_month": year_month, "job_id": job_id}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    result = run_no_income_nudge_job("cli")
    print(result)
    sys.exit(0)
