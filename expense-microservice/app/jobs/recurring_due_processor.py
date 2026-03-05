import argparse
import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from app.services.expense_data_service import ExpenseDataService
from app.services.service_factory import ServiceFactory

logger = logging.getLogger("expense_recurring_due_processor")


def _configure_logging(level: str) -> None:
    resolved_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logging.basicConfig(level=resolved_level, format="%(message)s")


def _log_json(level: str, **fields: Any) -> None:
    line = json.dumps(fields, default=str, separators=(",", ":"))
    if level == "error":
        logger.error(line)
    else:
        logger.info(line)


def _parse_as_of(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid --as-of date '{value}': {e}") from e


def run_recurring_due_processor(as_of_date: date, limit: int, job_id: str) -> int:
    service = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(service, ExpenseDataService):
        _log_json(
            "error",
            service="expense",
            component="recurring_due_processor",
            job_id=job_id,
            request_id=job_id,
            message="ExpenseDataService not available",
        )
        return 2

    started_at = datetime.now(timezone.utc).isoformat()
    _log_json(
        "info",
        service="expense",
        component="recurring_due_processor",
        event="started",
        job_id=job_id,
        request_id=job_id,
        as_of_date=as_of_date.isoformat(),
        limit=limit,
        started_at=started_at,
    )

    result = service.process_due_recurring_batch(as_of_date=as_of_date, limit=limit)

    for failure in result.get("failures", []):
        _log_json(
            "error",
            service="expense",
            component="recurring_due_processor",
            event="recurring_processing_failed",
            job_id=job_id,
            request_id=job_id,
            as_of_date=as_of_date.isoformat(),
            recurring_id=failure.get("recurring_id"),
            error=failure.get("error"),
        )

    _log_json(
        "info",
        service="expense",
        component="recurring_due_processor",
        event="completed",
        job_id=job_id,
        request_id=job_id,
        as_of_date=result.get("as_of_date"),
        candidate_count=result.get("candidate_count"),
        processed_count=result.get("processed_count"),
        skipped_count=result.get("skipped_count"),
        failed_count=result.get("failed_count"),
    )

    return 1 if int(result.get("failed_count", 0)) > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process due recurring expense templates and create expense rows.",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Process recurring items due on or before this date (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum due recurring templates to process in one run (default: 500).",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Optional job identifier for correlating logs. Default: generated UUID.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR). Default: INFO.",
    )
    args = parser.parse_args()

    _configure_logging(args.log_level)
    as_of_date = _parse_as_of(args.as_of)
    limit = max(1, int(args.limit or 1))
    job_id = str(args.job_id or uuid.uuid4())
    return run_recurring_due_processor(as_of_date=as_of_date, limit=limit, job_id=job_id)


if __name__ == "__main__":
    raise SystemExit(main())
