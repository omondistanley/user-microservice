"""
Weekly investment digest job.

Runs on Mondays (enforced by scheduler guard). For each user with recent activity,
generates a brief digest summarising portfolio changes and stores it in recommendation_digest.

Not financial advice. All output is informational.
"""
import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import psycopg2

from app.core.config import (
    DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER,
)

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "investments_db",
        connect_timeout=5,
    )


def _get_active_users(conn) -> List[int]:
    """Users who have run a recommendation in the last 30 days."""
    cutoff = date.today() - timedelta(days=30)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT user_id FROM recommendation_run WHERE created_at >= %s",
            (cutoff.isoformat(),),
        )
        return [row[0] for row in cur.fetchall()]


def _get_latest_health(conn, user_id: int) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT score, tier, flags_json FROM portfolio_health_snapshot
               WHERE user_id = %s ORDER BY snapshot_date DESC LIMIT 1""",
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            flags = row[2] if isinstance(row[2], list) else (json.loads(row[2]) if row[2] else [])
            return {"score": row[0], "tier": row[1], "flags": flags}
    return None


def _get_prior_health(conn, user_id: int) -> Optional[int]:
    week_ago = date.today() - timedelta(days=7)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT score FROM portfolio_health_snapshot
               WHERE user_id = %s AND snapshot_date <= %s
               ORDER BY snapshot_date DESC LIMIT 1""",
            (user_id, week_ago.isoformat()),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _build_digest(user_id: int, health: Dict[str, Any], prior_score: Optional[int]) -> Dict[str, Any]:
    score = health["score"]
    tier = health["tier"]
    flags = health.get("flags", [])

    if prior_score is not None:
        delta = score - prior_score
        change_str = f"up {delta}" if delta > 0 else (f"down {abs(delta)}" if delta < 0 else "unchanged")
        headline = f"Portfolio health score {change_str} this week ({score}/100)"
    else:
        headline = f"Portfolio health score: {score}/100 — {tier}"

    flag_text = f" One thing to note: {flags[0]}." if flags else ""
    body = (
        f"Your portfolio health score is {score}/100 ({tier}).{flag_text} "
        "This is informational only, not financial advice."
    )

    return {
        "user_id": user_id,
        "week_start_date": (date.today() - timedelta(days=date.today().weekday())).isoformat(),
        "headline": headline,
        "body_text": body,
        "portfolio_score": score,
        "digest_json": json.dumps({"score": score, "tier": tier, "flags": flags}),
    }


def _upsert_digest(conn, digest: Dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO recommendation_digest
                   (user_id, week_start_date, headline, body_text, portfolio_score, digest_json)
               VALUES (%(user_id)s, %(week_start_date)s, %(headline)s, %(body_text)s,
                       %(portfolio_score)s, %(digest_json)s)
               ON CONFLICT (user_id, week_start_date)
               DO UPDATE SET headline = EXCLUDED.headline,
                             body_text = EXCLUDED.body_text,
                             portfolio_score = EXCLUDED.portfolio_score,
                             digest_json = EXCLUDED.digest_json""",
            digest,
        )
    conn.commit()


def run_investment_digest_job(job_id: str = "") -> Dict[str, Any]:
    """
    Generate weekly digests for all active users.
    Should only run on Mondays — the scheduler enforces this.
    """
    logger.info("[digest_job:%s] starting", job_id)
    processed = 0
    errors: List[str] = []

    try:
        conn = _get_conn()
        try:
            users = _get_active_users(conn)
            logger.info("[digest_job:%s] %d active users", job_id, len(users))

            for user_id in users:
                try:
                    health = _get_latest_health(conn, user_id)
                    if not health:
                        continue
                    prior_score = _get_prior_health(conn, user_id)
                    digest = _build_digest(user_id, health, prior_score)
                    _upsert_digest(conn, digest)
                    processed += 1
                except Exception as e:
                    errors.append(f"user {user_id}: {e}")
                    logger.warning("[digest_job:%s] user %d error: %s", job_id, user_id, e)
        finally:
            conn.close()
    except Exception as e:
        errors.append(str(e))
        logger.exception("[digest_job:%s] connection error: %s", job_id, e)

    logger.info("[digest_job:%s] done. processed=%d errors=%d", job_id, processed, len(errors))
    return {"processed": processed, "errors": errors}
