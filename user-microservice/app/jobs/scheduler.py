"""
Simple scheduler for user-side jobs.
- webhook processor (high frequency)
- retention purge (daily cadence)
- digest sender (weekly/monthly cadence)
"""
import os
import time
import uuid
from datetime import datetime, timezone

from app.jobs.digest_sender import run as run_digest
from app.jobs.retention_purge import run as run_retention_purge
from app.jobs.webhook_processor import run_once as run_webhook_processor
from app.jobs.monthly_close_notification_job import run_monthly_close_notification_job


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def main():
    interval = int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "60"))
    while True:
        now = datetime.now(timezone.utc)
        today = now.date()

        # always run webhook processor on each scheduler tick
        run_webhook_processor()

        # daily retention purge close to 00:00 UTC (first five minutes)
        if now.hour == 0 and now.minute < 5:
            run_retention_purge(as_of=today, dry_run=False)

        # weekly digest on Mondays close to 07:00 UTC
        if now.weekday() == 0 and now.hour == 7 and now.minute < 5:
            run_digest(as_of=today, dry_run=False, frequency="weekly")

        # monthly digest on first day close to 08:00 UTC
        if today.day == 1 and now.hour == 8 and now.minute < 5:
            run_digest(as_of=today, dry_run=False, frequency="monthly")

        # monthly close notification on 1st of month close to 09:00 UTC
        if today.day == 1 and now.hour == 9 and now.minute < 5:
            try:
                run_monthly_close_notification_job(job_id=str(uuid.uuid4()))
            except Exception as e:
                pass  # logged inside job

        # fixed sleep keeps implementation simple and dependency-free
        time.sleep(max(15, interval))


if __name__ == "__main__":
    main()
