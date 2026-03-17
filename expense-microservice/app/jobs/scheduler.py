"""
Simple scheduler for expense jobs.
Runs recurring due processor, exchange rate sync, and alert/nudge jobs on intervals.
"""
import os
import time
from datetime import date
from uuid import uuid4

from app.jobs.exchange_rate_sync import run_exchange_rate_sync
from app.jobs.recurring_due_processor import run_recurring_due_processor
from app.jobs.no_income_nudge_job import run_no_income_nudge_job
from app.jobs.low_projected_balance_job import run_low_projected_balance_job


def main():
    interval = int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "3600"))
    source = os.environ.get("EXCHANGE_RATE_SOURCE", "ECB")
    while True:
        today = date.today()
        run_recurring_due_processor(as_of_date=today, limit=500, job_id=str(uuid4()))
        run_exchange_rate_sync(target_date=today, source=source, csv_path=None, job_id=str(uuid4()))
        run_no_income_nudge_job(job_id=str(uuid4()))
        run_low_projected_balance_job(job_id=str(uuid4()))
        time.sleep(max(300, interval))


if __name__ == "__main__":
    main()
