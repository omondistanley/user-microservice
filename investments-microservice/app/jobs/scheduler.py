"""
Simple scheduler for investments jobs.

Runs Alpaca sync plus rebalance automation on an interval.
Each job internally checks whether there is work due, so this loop can be frequent.

Run: python -m app.jobs.scheduler
"""
import datetime
import logging
import os
import time
import uuid

from app.jobs.alpaca_sync import run_alpaca_sync
from app.jobs.rebalance_watch_job import run_rebalance_watch_job
from app.jobs.rebalance_buy_job import run_rebalance_buy_job
from app.jobs.investment_digest_job import run_investment_digest_job
from app.jobs.watchlist_alert_job import run_watchlist_alert_job
from app.jobs.investment_nudge_job import run_investment_nudge_job
from app.jobs.vix_monitor_job import run_vix_monitor_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INTERVAL_SECONDS = int(os.environ.get("INVESTMENTS_SCHEDULER_INTERVAL_SECONDS", "3600"))


def main():
    while True:
        try:
            now = datetime.datetime.utcnow()

            run_alpaca_sync(job_id=str(uuid.uuid4()))
            run_rebalance_watch_job(job_id=str(uuid.uuid4()))
            run_rebalance_buy_job(job_id=str(uuid.uuid4()))

            if now.weekday() == 0:  # Monday only
                try:
                    run_investment_digest_job(job_id=str(uuid.uuid4()))
                except Exception as e:
                    logger.exception("digest job failed: %s", e)

            # Daily: nudge job (runs once per day, rate-limiting handled internally)
            if now.hour == 9 and now.minute < 5:
                try:
                    run_investment_nudge_job(job_id=str(uuid.uuid4()))
                except Exception as e:
                    logger.exception("nudge job failed: %s", e)

            # Daily afternoon: watchlist alert check (after market close ~16:30 UTC)
            if now.hour == 21 and now.minute < 5:
                try:
                    run_watchlist_alert_job(job_id=str(uuid.uuid4()))
                except Exception as e:
                    logger.exception("watchlist alert job failed: %s", e)

            # Daily: VIX monitor (morning pre-market check)
            if now.hour == 13 and now.minute < 5:
                try:
                    run_vix_monitor_job(job_id=str(uuid.uuid4()))
                except Exception as e:
                    logger.exception("vix monitor job failed: %s", e)

        except Exception as e:
            logger.exception("scheduler job failed: %s", e)
        time.sleep(max(60, INTERVAL_SECONDS))


if __name__ == "__main__":
    main()
