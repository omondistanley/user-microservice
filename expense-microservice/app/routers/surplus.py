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
SCHEMA = "expenses_db"


def _get_conn():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "expenses_db",
        connect_timeout=5,
        options=f"-c search_path={SCHEMA}",
    )


def _income_totals_last_three_months(user_id: int) -> List[float]:
    """Sum of income per calendar month for up to the last 3 distinct months (partial window)."""
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT SUM(amount) AS s
                    FROM expenses_db.income
                    WHERE user_id = %s
                      AND date >= (CURRENT_DATE - INTERVAL '120 days')
                    GROUP BY TO_CHAR(date, 'YYYY-MM')
                    ORDER BY TO_CHAR(date, 'YYYY-MM') DESC
                    LIMIT 3
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                return [float(r[0]) for r in rows if r and r[0] is not None]
        finally:
            conn.close()
    except Exception as e:
        logger.debug("income three-month buckets: %s", e)
    return []


def _get_monthly_income(user_id: int, months: int = 1) -> float:
    """Sum of income records for the last N months."""
    cutoff = date.today() - timedelta(days=30 * months)
    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT COALESCE(SUM(amount), 0) FROM "{SCHEMA}"."income" WHERE user_id = %s AND date >= %s',
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
                    FROM expenses_db.recurring_expense
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
                       FROM expenses_db.expense
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
                    FROM expenses_db.savings_goal
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
                    FROM expenses_db.user_irregular_expense
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
    income_3m_avg = _get_monthly_income(user_id, months=3)
    month_buckets = _income_totals_last_three_months(user_id)
    p25_income = income
    cv_income = 0.0
    if month_buckets:
        sorted_b = sorted(month_buckets)
        p25_income = float(sorted_b[max(0, len(sorted_b) // 4)])
        m_b = sum(month_buckets) / len(month_buckets)
        if m_b > 0 and len(month_buckets) >= 2:
            var_b = sum((x - m_b) ** 2 for x in month_buckets) / (len(month_buckets) - 1)
            cv_income = (var_b**0.5) / m_b
    income_mode = "variable" if cv_income > 0.15 else "steady"

    fixed_recurring = _get_fixed_recurring(user_id)
    variable_avg = _get_variable_avg(user_id, months=3)
    goal_contributions = _get_goal_contributions(user_id)
    irregular_reserve = _get_irregular_reserve(user_id)

    total_expenses = fixed_recurring + variable_avg + goal_contributions + irregular_reserve
    investable_surplus = income - total_expenses
    investable_surplus_p25 = p25_income - total_expenses

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
        "income_3m_avg": round(income_3m_avg, 2),
        "income_mode": income_mode,
        "income_cv": round(cv_income, 4),
        "income_p25_monthly_estimate": round(p25_income, 2),
        "fixed_recurring": round(fixed_recurring, 2),
        "variable_avg": round(variable_avg, 2),
        "goal_contributions": round(goal_contributions, 2),
        "irregular_reserve": round(irregular_reserve, 2),
        "investable_surplus": round(investable_surplus, 2),
        "investable_surplus_p25_path": round(investable_surplus_p25, 2),
        "waterfall": waterfall,
        "disclaimer": "Not financial advice. For informational purposes only.",
    }
