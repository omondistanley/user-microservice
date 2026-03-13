"""
Simple scheduler for budget jobs.
Runs budget alert evaluation on fixed intervals.
"""
import os
import time
from datetime import date
from uuid import uuid4

from app.jobs.budget_alert_processor import run_budget_alert_processor


def main():
    interval = int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "1800"))
    while True:
        run_budget_alert_processor(as_of_date=date.today(), user_id=None, job_id=str(uuid4()))
        time.sleep(max(300, interval))


if __name__ == "__main__":
    main()
