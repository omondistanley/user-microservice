"""
Round-up job: for each active round_up_config, sum round-up deltas from expenses
created since last run and create one goal contribution with source='round_up'.
"""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import ceil

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.services.expense_data_service import ExpenseDataService
from app.services.goal_data_service import GoalDataService

logger = logging.getLogger(__name__)

DB_CONTEXT = {
    "host": DB_HOST or "localhost",
    "port": int(DB_PORT) if DB_PORT else 5432,
    "user": DB_USER or "postgres",
    "password": DB_PASSWORD or "postgres",
    "dbname": DB_NAME or "expenses_db",
}


def _round_up_delta(amount: Decimal, round_to: Decimal) -> Decimal:
    """Round amount up to next multiple of round_to; return the delta (e.g. round_to=1 -> ceil(amount) - amount)."""
    if round_to <= 0:
        return Decimal("0")
    # next multiple of round_to >= amount
    n = Decimal(ceil(float(amount / round_to)))
    next_val = n * round_to
    return max(Decimal("0"), next_val - amount)


def run_round_up_job(job_id: str = "") -> dict:
    """
    For each active round_up_config: fetch expenses created since last_processed_at,
    sum round-up deltas, add one goal contribution, mark processed.
    """
    goal_svc = GoalDataService(context=DB_CONTEXT)
    expense_svc = ExpenseDataService(context=DB_CONTEXT)
    configs = goal_svc.list_all_active_round_up_configs()
    processed = 0
    errors = []
    now = datetime.now(timezone.utc)
    default_since = now - timedelta(days=1)
    for cfg in configs:
        try:
            user_id = int(cfg["user_id"])
            goal_id = cfg["goal_id"]
            config_id = str(cfg["id"])
            round_to = Decimal(str(cfg.get("round_to") or "1"))
            last_at = cfg.get("last_processed_at")
            since = last_at if last_at else default_since
            if hasattr(since, "tzinfo") and since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            expenses = expense_svc.list_expenses_created_since(user_id, since)
            total_delta = Decimal("0")
            for row in expenses:
                amt = Decimal(str(row.get("amount") or "0"))
                total_delta += _round_up_delta(amt, round_to)
            if total_delta > 0:
                goal_svc.add_contribution(
                    goal_id,
                    user_id,
                    total_delta,
                    now.date(),
                    "round_up",
                )
            goal_svc.mark_round_up_processed(config_id, user_id, when=now)
            processed += 1
        except Exception as e:
            logger.exception("round_up_job config %s error: %s", cfg.get("id"), e)
            errors.append({"config_id": str(cfg.get("id")), "error": str(e)})
    return {"processed": processed, "errors": errors, "job_id": job_id}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    result = run_round_up_job("cli")
    print(result)
    sys.exit(0 if not result.get("errors") else 1)
