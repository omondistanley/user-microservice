"""
Simple scheduler for investments jobs. Runs Alpaca sync on an interval.
Run: python -m app.jobs.scheduler
"""
import logging
import os
import time
import uuid

from app.jobs.alpaca_sync import run_alpaca_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INTERVAL_SECONDS = int(os.environ.get("INVESTMENTS_SCHEDULER_INTERVAL_SECONDS", "3600"))


def main():
    while True:
        try:
            run_alpaca_sync(job_id=str(uuid.uuid4()))
        except Exception as e:
            logger.exception("alpaca_sync failed: %s", e)
        time.sleep(max(60, INTERVAL_SECONDS))


if __name__ == "__main__":
    main()
