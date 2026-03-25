"""
Surplus waterfall endpoint.

Returns a breakdown of monthly surplus after all committed expenses:
  income - fixed_recurring - variable_avg - goal_contributions - irregular_reserve = investable_surplus

Informational only. Not financial advice.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import APIRouter, Depends, Query

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.core.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["surplus"])


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "expenses_db",
        connect_timeout=5,
    )


def _get_monthly_income(user_id: int, months: int = 1) -> float:
    """Sum of income records for the last N months."""
    cutoff = date.today() - timedelta(days=30 * months)
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM income WHERE user_id = %s AND date >= %s",
                    (user_id, cutoff.isoformat()),
                )
                row = cur.fetchone()
                total = float(row[0]) if row else 0.0
                return total / months if months > 1 else total
        finally:
            conn.close()
    except Exception as e:
        logger.debug("get_monthly_income error: %s", e)
    return 0.0


def _get_fixed_recurring(user_id: int) -> float:
    """Sum of active monthly recurring expenses."""
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(
                        CASE frequency
                            WHEN 'weekly'     THEN amount * 4.33
                            WHEN 'biweekly'   THEN amount * 2.17
                            WHEN 'monthly'    THEN amount
                            WHEN 'quarterly'  THEN amount / 3
                            WHEN 'annual'     THEN amount / 12
                            ELSE amount
                        END
                    ), 0)
                    FROM recurring_expense
                    WHERE user_id = %s AND (end_date IS NULL OR end_date >= CURRENT_DATE)""",
                    (user_id,),
                )
                row = cur.fetchone()
                return float(row[0]) if row else 0.0
        finally:
            conn.close()
    except Exception as e:
        logger.debug("get_fixed_recurring error: %s", e)
    return 0.0


def _get_variable_avg(user_id: int, months: int = 3) -> float:
    """3-month average of non-recurring expenses."""
    cutoff = date.today() - timedelta(days=30 * months)
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(amount), 0)
                       FROM expense
                       WHERE user_id = %s AND date >= %s AND deleted_at IS NULL""",
                    (user_id, cutoff.isoformat()),
                )
                row = cur.fetchone()
                total = float(row[0]) if row else 0.0
                return total / months
        finally:
            conn.close()
    except Exception as e:
        logger.debug("get_variable_avg error: %s", e)
    return 0.0


def _get_goal_contributions(user_id: int) -> float:
    """Monthly contributions across active savings goals."""
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(
                        CASE
                            WHEN target_date IS NOT NULL AND target_date > CURRENT_DATE
                            THEN (target_amount - COALESCE(current_amount, 0)) /
                                 GREATEST(1, EXTRACT(MONTH FROM AGE(target_date, CURRENT_DATE)))
                            ELSE 0
                        END
                    ), 0)
                    FROM savings_goal
                    WHERE user_id = %s AND (is_completed IS NULL OR is_completed = FALSE)""",
                    (user_id,),
                )
                row = cur.fetchone()
                return float(row[0]) if row else 0.0
        finally:
            conn.close()
    except Exception as e:
        logger.debug("get_goal_contributions error: %s", e)
    return 0.0


def _get_irregular_reserve(user_id: int) -> float:
    """Monthly reserve for irregular expenses."""
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COALESCE(SUM(
                        CASE frequency
                            WHEN 'annual'    THEN estimated_amount / 12
                            WHEN 'quarterly' THEN estimated_amount / 3
                            ELSE estimated_amount
                        END
                    ), 0)
                    FROM user_irregular_expense
                    WHERE user_id = %s""",
                    (user_id,),
                )
                row = cur.fetchone()
                return float(row[0]) if row else 0.0
        finally:
            conn.close()
    except Exception as e:
        logger.debug("get_irregular_reserve error: %s", e)
    return 0.0


@router.get("/surplus", response_model=dict)
async def get_surplus(
    user_id: int = Depends(get_current_user_id),
):
    """
    Surplus waterfall: income - expenses - goals - irregular reserve = investable surplus.
    Informational only. Not financial advice.
    """
    income = _get_monthly_income(user_id, months=1)
    fixed_recurring = _get_fixed_recurring(user_id)
    variable_avg = _get_variable_avg(user_id, months=3)
    goal_contributions = _get_goal_contributions(user_id)
    irregular_reserve = _get_irregular_reserve(user_id)

    total_expenses = fixed_recurring + variable_avg + goal_contributions + irregular_reserve
    investable_surplus = income - total_expenses

    waterfall = [
        {"label": "Monthly income", "amount": round(income, 2), "type": "income"},
        {"label": "Fixed recurring", "amount": round(fixed_recurring, 2), "type": "expense"},
        {"label": "Variable (3-month avg)", "amount": round(variable_avg, 2), "type": "expense"},
        {"label": "Goal contributions", "amount": round(goal_contributions, 2), "type": "expense"},
        {"label": "Irregular reserve", "amount": round(irregular_reserve, 2), "type": "expense"},
        {
            "label": "Available to invest",
            "amount": round(investable_surplus, 2),
            "type": "surplus" if investable_surplus >= 0 else "deficit",
        },
    ]

    return {
        "income": round(income, 2),
        "fixed_recurring": round(fixed_recurring, 2),
        "variable_avg": round(variable_avg, 2),
        "goal_contributions": round(goal_contributions, 2),
        "irregular_reserve": round(irregular_reserve, 2),
        "investable_surplus": round(investable_surplus, 2),
        "waterfall": waterfall,
        "disclaimer": "Not financial advice. For informational purposes only.",
    }
