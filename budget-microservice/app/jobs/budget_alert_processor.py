import argparse
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx

from app.core.config import INTERNAL_API_KEY, USER_SERVICE_INTERNAL_URL
from app.services.budget_data_service import BudgetDataService
from app.services.service_factory import ServiceFactory

logger = logging.getLogger("budget_alert_processor")


def _log_json(level: str, **fields):
    line = json.dumps(fields, default=str, separators=(",", ":"))
    if level == "error":
        logger.error(line)
    else:
        logger.info(line)


def _data_service() -> BudgetDataService:
    ds = ServiceFactory.get_service("BudgetDataService")
    if not isinstance(ds, BudgetDataService):
        raise RuntimeError("BudgetDataService not available")
    return ds


def _notify_user_service(event: Dict[str, Any], request_id: str) -> None:
    if not USER_SERVICE_INTERNAL_URL:
        return
    headers = {"x-request-id": request_id}
    if INTERNAL_API_KEY:
        headers["x-internal-api-key"] = INTERNAL_API_KEY
    payload = {
        "user_id": event["user_id"],
        "type": "budget_alert",
        "title": "Budget threshold reached",
        "body": (
            f"Budget reached {event['threshold_percent']}% "
            f"({event['spent_amount']} spent of {event['budget_amount']})."
        ),
        "payload": {
            "budget_id": str(event["budget_id"]),
            "period_start": str(event["period_start"]),
            "period_end": str(event["period_end"]),
            "threshold_percent": str(event["threshold_percent"]),
            "spent_amount": str(event["spent_amount"]),
            "budget_amount": str(event["budget_amount"]),
            "channel": event["channel"],
        },
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{USER_SERVICE_INTERNAL_URL}/internal/v1/notifications/budget-alert",
            json=payload,
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"notification_write_failed:{resp.status_code}")


def evaluate_budget_alerts(
    as_of_date: date,
    user_id: Optional[int] = None,
    request_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    ds = _data_service()
    rid = request_id or str(uuid4())
    targets = ds.list_active_budget_alert_targets(as_of_date=as_of_date, user_id=user_id)

    processed_count = 0
    sent_count = 0
    skipped_count = 0
    failed_count = 0
    failures: list[Dict[str, str]] = []

    for target in targets:
        processed_count += 1
        try:
            budget_amount = Decimal(str(target["budget_amount"]))
            if budget_amount <= 0:
                skipped_count += 1
                continue
            spent_amount = ds.get_spent_amount(
                user_id=int(target["user_id"]),
                category_code=int(target["category_code"]),
                period_start=target["period_start"],
                period_end=target["period_end"],
            )
            threshold_percent = Decimal(str(target["threshold_percent"]))
            spent_percent = (spent_amount / budget_amount) * Decimal("100")
            if spent_percent < threshold_percent:
                skipped_count += 1
                continue

            event = ds.create_budget_alert_event(
                user_id=int(target["user_id"]),
                budget_id=str(target["budget_id"]),
                period_start=target["period_start"],
                period_end=target["period_end"],
                threshold_percent=threshold_percent,
                spent_amount=spent_amount,
                budget_amount=budget_amount,
                channel=str(target["channel"]),
            )
            if not event:
                skipped_count += 1
                continue

            _notify_user_service(event, rid)
            sent_count += 1
        except Exception as e:
            failed_count += 1
            failures.append(
                {
                    "budget_id": str(target.get("budget_id")),
                    "error": str(e),
                }
            )

    result = {
        "as_of_date": as_of_date.isoformat(),
        "candidate_count": len(targets),
        "processed_count": processed_count,
        "sent_count": sent_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "failures": failures,
        "request_id": rid,
    }
    if job_id:
        result["job_id"] = job_id
    _log_json("info", service="budget", action="budget_alert_evaluate", **result)
    return result


def run_budget_alert_processor(
    as_of_date: date,
    user_id: Optional[int] = None,
    job_id: Optional[str] = None,
) -> int:
    result = evaluate_budget_alerts(as_of_date=as_of_date, user_id=user_id, job_id=job_id)
    return 0 if result["failed_count"] == 0 else 1


def _parse_date(value: Optional[str]) -> date:
    if not value:
        return datetime.utcnow().date()
    return date.fromisoformat(value)


def main():
    parser = argparse.ArgumentParser(description="Evaluate budget alerts and emit events/notifications.")
    parser.add_argument("--as-of", dest="as_of", help="Date in YYYY-MM-DD format (default: today UTC)")
    parser.add_argument("--user-id", dest="user_id", type=int, default=None, help="Optional single-user scope")
    parser.add_argument("--job-id", dest="job_id", default=None, help="Optional correlation id")
    args = parser.parse_args()

    as_of_date = _parse_date(args.as_of)
    code = run_budget_alert_processor(as_of_date=as_of_date, user_id=args.user_id, job_id=args.job_id)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
