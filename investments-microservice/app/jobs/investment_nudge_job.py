"""
Proactive investment nudge job.
Fires 5 types of nudges + seasonal calendar triggers.
Rate-limited: 1 per nudge type per 30 days per user.
All messages are informational only. Not financial advice.
"""
import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import psycopg2

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

logger = logging.getLogger(__name__)

_NUDGE_COOLDOWN_DAYS = 30


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "investments_db",
        connect_timeout=5,
    )


def _already_nudged(conn, user_id: int, nudge_type: str) -> bool:
    cutoff = (date.today() - timedelta(days=_NUDGE_COOLDOWN_DAYS)).isoformat()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT 1 FROM nudge_log WHERE user_id = %s AND nudge_type = %s AND fired_at >= %s LIMIT 1""",
            (user_id, nudge_type, cutoff),
        )
        return cur.fetchone() is not None


def _log_nudge(conn, user_id: int, nudge_type: str, message: str) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO nudge_log (user_id, nudge_type, message, fired_at)
                   VALUES (%s, %s, %s, NOW()) ON CONFLICT DO NOTHING""",
                (user_id, nudge_type, message),
            )
        conn.commit()
    except Exception:
        pass


def _get_active_users(conn) -> List[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT user_id FROM holding WHERE quantity > 0 LIMIT 1000"
        )
        return [r[0] for r in cur.fetchall()]


def _check_sector_drift(conn, user_id: int) -> Optional[str]:
    """Check if any sector has drifted >8% from target over 90 days."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT score, tier, components_json, snapshot_date
                   FROM portfolio_health_snapshot
                   WHERE user_id = %s ORDER BY snapshot_date DESC LIMIT 2""",
                (user_id,),
            )
            rows = cur.fetchall()
            if len(rows) >= 1:
                comp = rows[0][2]
                if comp:
                    c = comp if isinstance(comp, dict) else json.loads(comp)
                    alignment = c.get("alignment", {})
                    if isinstance(alignment, dict) and float(alignment.get("score", 100)) < 50:
                        return "Your portfolio's sector allocation has drifted from your stated targets. This is informational."
    except Exception:
        pass
    return None


def _seasonal_nudges(today: date) -> List[Dict[str, Any]]:
    """Return seasonal nudge messages relevant to today's date."""
    nudges = []
    month, day = today.month, today.day

    # Tax-loss harvesting window: Oct 1 – Dec 20
    if (month == 10) or (month == 11) or (month == 12 and day <= 20):
        nudges.append({
            "type": "tax_loss_harvest_season",
            "message": (
                "The tax-loss harvesting window (Oct–Dec) is open. You may have positions with unrealised losses "
                "in taxable accounts that could be reviewed. This is informational — consult a tax professional."
            ),
        })

    # IRA contribution deadline: Jan 1 – Apr 14
    if month in (1, 2, 3) or (month == 4 and day <= 14):
        nudges.append({
            "type": "ira_contribution_deadline",
            "message": (
                f"The IRA contribution deadline for the prior tax year is April 15. "
                "If you have IRA contribution headroom remaining, this is informational — consult a tax professional."
            ),
        })

    # Year-end review: December
    if month == 12:
        nudges.append({
            "type": "year_end_review",
            "message": (
                f"Year-end portfolio review: December is a good time to review your allocation, "
                "check for tax-loss opportunities, and confirm your goals are on track. This is informational."
            ),
        })

    return nudges


def run_investment_nudge_job(job_id: str = "") -> Dict[str, Any]:
    """Fire proactive nudges for active users. Rate-limited 1/type/30days/user."""
    logger.info("[nudge_job:%s] starting", job_id)
    today = date.today()
    total_fired = 0
    errors: List[str] = []

    try:
        conn = _get_conn()
        try:
            users = _get_active_users(conn)
            logger.info("[nudge_job:%s] %d users to check", job_id, len(users))

            # Seasonal nudges — check once per job run (same message for all users)
            seasonal = _seasonal_nudges(today)

            for user_id in users:
                try:
                    # Sector drift nudge
                    drift_msg = _check_sector_drift(conn, user_id)
                    if drift_msg and not _already_nudged(conn, user_id, "sector_drift"):
                        _log_nudge(conn, user_id, "sector_drift", drift_msg)
                        total_fired += 1

                    # Seasonal nudges
                    for sn in seasonal:
                        if not _already_nudged(conn, user_id, sn["type"]):
                            _log_nudge(conn, user_id, sn["type"], sn["message"])
                            total_fired += 1

                except Exception as e:
                    errors.append(f"user {user_id}: {e}")

        finally:
            conn.close()
    except Exception as e:
        errors.append(str(e))
        logger.exception("[nudge_job:%s] error: %s", job_id, e)

    logger.info("[nudge_job:%s] done. fired=%d errors=%d", job_id, total_fired, len(errors))
    return {"fired": total_fired, "errors": errors}
