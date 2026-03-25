"""
Monthly close notification job.
Runs on the 1st of each month. Sends a 3-sentence portfolio summary notification.
Not financial advice. All content is informational.
"""
import json
import logging
from datetime import date
from typing import Any, Dict, List

import psycopg2
import requests

from app.core.config import (
    DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER,
    INVESTMENTS_SERVICE_URL,
)

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        connect_timeout=5,
    )


def _get_users_with_notifications(conn) -> List[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT user_id FROM user_notification ORDER BY user_id LIMIT 500")
        return [r[0] for r in cur.fetchall()]


def _insert_notification(conn, user_id: int, title: str, body: str) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO user_notification (user_id, type, title, body)
                   VALUES (%s, %s, %s, %s)""",
                (user_id, "monthly_close", title, body),
            )
        conn.commit()
    except Exception as e:
        logger.debug("insert_notification error: %s", e)


def run_monthly_close_notification_job(job_id: str = "") -> Dict[str, Any]:
    """
    Only runs on the 1st of the month (caller or scheduler enforces this).
    Sends a brief informational monthly close notification to each user.
    """
    today = date.today()
    if today.day != 1:
        logger.info("[monthly_close:%s] skipped — not 1st of month", job_id)
        return {"skipped": True, "reason": "not 1st of month"}

    month_label = today.strftime("%B %Y")
    logger.info("[monthly_close:%s] running for %s", job_id, month_label)

    processed = 0
    errors: List[str] = []

    try:
        conn = _get_conn()
        try:
            users = _get_users_with_notifications(conn)
            for user_id in users:
                try:
                    title = f"{month_label} portfolio summary"
                    body = (
                        f"Your {month_label} portfolio summary is ready. "
                        "Log in to review your holdings, check your health score, and see what changed. "
                        "This is informational — not financial advice."
                    )
                    _insert_notification(conn, user_id, title, body)
                    processed += 1
                except Exception as e:
                    errors.append(f"user {user_id}: {e}")
        finally:
            conn.close()
    except Exception as e:
        errors.append(str(e))
        logger.exception("[monthly_close:%s] error: %s", job_id, e)

    logger.info("[monthly_close:%s] done. processed=%d errors=%d", job_id, processed, len(errors))
    return {"processed": processed, "errors": errors}
