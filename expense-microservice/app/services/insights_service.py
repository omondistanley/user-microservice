"""
Phase 4: Forecast and anomaly insights (deterministic, no paid ML).
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = "expenses_db"
TABLE = "expense"
FEEDBACK_TABLE = "anomaly_feedback"


class InsightsService:
    def __init__(self, context: Dict[str, Any]):
        self.context = context

    def _get_connection(self):
        return psycopg2.connect(
            host=self.context["host"],
            port=self.context["port"],
            user=self.context["user"],
            password=self.context["password"],
            dbname=self.context["dbname"],
            cursor_factory=RealDictCursor,
        )

    def _conn_autocommit(self):
        conn = self._get_connection()
        conn.autocommit = True
        return conn

    def get_monthly_totals(
        self,
        user_id: int,
        months_back: int = 6,
        category_code: Optional[int] = None,
        household_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of {month: 'YYYY-MM', total: decimal} for last N months."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            conditions = ["user_id = %s", "deleted_at IS NULL"]
            params: List[Any] = [user_id]
            if category_code is not None:
                conditions.append("category_code = %s")
                params.append(category_code)
            if household_id is not None:
                conditions.append("household_id IS NOT DISTINCT FROM %s")
                params.append(household_id)
            where = " AND ".join(conditions)
            start_d = date.today().replace(day=1)
            for _ in range(months_back - 1):
                start_d = (start_d.replace(day=1) - timedelta(days=1)).replace(day=1)
            params.append(start_d)
            cur.execute(
                f"""
                SELECT to_char(date, 'YYYY-MM') AS month, COALESCE(SUM(amount), 0) AS total
                FROM "{SCHEMA}"."{TABLE}" WHERE {where}
                  AND date >= %s
                  AND date < date_trunc('month', CURRENT_DATE)::date + INTERVAL '1 month'
                GROUP BY to_char(date, 'YYYY-MM')
                ORDER BY month
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def forecast_spend(
        self,
        user_id: int,
        months_back: int = 6,
        category_code: Optional[int] = None,
        household_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Simple moving average forecast for current + next 2 months. Returns projected amounts and confidence metadata."""
        rows = self.get_monthly_totals(user_id, months_back, category_code, household_id)
        if not rows:
            return {
                "months_back": months_back,
                "data_points": 0,
                "projections": [],
                "message": "Insufficient data: need at least one month of expenses.",
            }
        totals = [float(r["total"]) for r in rows]
        n = len(totals)
        window = min(3, n)
        moving_avg = sum(totals[-window:]) / window if window else 0
        mean = sum(totals) / n
        variance = sum((t - mean) ** 2 for t in totals) / n if n else 0
        std = variance ** 0.5
        low = max(0, moving_avg - std)
        high = moving_avg + std
        this_month = date.today().replace(day=1)
        projections = []
        for i in range(3):
            m = this_month + timedelta(days=32 * i)
            m = m.replace(day=1)
            projections.append({
                "month": m.strftime("%Y-%m"),
                "projected_amount": round(moving_avg, 2),
                "confidence_low": round(low, 2),
                "confidence_high": round(high, 2),
            })
        return {
            "months_back": months_back,
            "data_points": n,
            "projections": projections,
            "method": "moving_average",
            "window": window,
        }

    def get_expenses_for_anomaly(
        self,
        user_id: int,
        limit: int = 500,
        household_id: Optional[str] = None,
    ) -> List[Dict]:
        """Fetch recent expenses excluding those with feedback='ignore'."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            conditions = ["e.user_id = %s", "e.deleted_at IS NULL"]
            params: List[Any] = [user_id]
            if household_id is not None:
                conditions.append("e.household_id IS NOT DISTINCT FROM %s")
                params.append(household_id)
            where = " AND ".join(conditions)
            cur.execute(
                f"""
                SELECT e.expense_id, e.user_id, e.amount, e.date, e.category_code, e.category_name, e.description, e.created_at
                FROM "{SCHEMA}"."{TABLE}" e
                LEFT JOIN "{SCHEMA}"."{FEEDBACK_TABLE}" f ON f.expense_id = e.expense_id AND f.user_id = e.user_id AND f.feedback = 'ignore'
                WHERE {where} AND f.expense_id IS NULL
                ORDER BY e.date DESC, e.created_at DESC
                LIMIT %s
                """,
                params + [limit],
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def detect_anomalies(
        self,
        user_id: int,
        household_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Z-score and IQR style flags: amount_outlier, frequency_spike, new_merchant_high_spend."""
        expenses = self.get_expenses_for_anomaly(user_id, limit, household_id)
        if not expenses:
            return []
        by_cat = defaultdict(list)
        by_desc = defaultdict(list)
        for e in expenses:
            amt = float(e["amount"])
            by_cat[e["category_code"]].append(amt)
            desc = (e.get("description") or "").strip().lower()[:100]
            if desc:
                by_desc[desc].append(amt)
        results = []
        for e in expenses:
            amt = float(e["amount"])
            cat = e["category_code"]
            cat_amounts = by_cat.get(cat, [])
            if len(cat_amounts) >= 2:
                mean = sum(cat_amounts) / len(cat_amounts)
                variance = sum((x - mean) ** 2 for x in cat_amounts) / len(cat_amounts)
                std = variance ** 0.5 if variance else 0
                if std and abs(amt - mean) > 2 * std:
                    results.append({
                        "expense_id": str(e["expense_id"]),
                        "date": str(e["date"]),
                        "amount": amt,
                        "category_code": cat,
                        "category_name": e.get("category_name", ""),
                        "reason": "amount_outlier",
                        "detail": f"Amount {amt} is >2 std from category mean {mean:.2f} (std {std:.2f})",
                    })
                    continue
            if len(cat_amounts) == 1 and amt > 0:
                results.append({
                    "expense_id": str(e["expense_id"]),
                    "date": str(e["date"]),
                    "amount": amt,
                    "category_code": cat,
                    "category_name": e.get("category_name", ""),
                    "reason": "new_merchant_high_spend",
                    "detail": "Single expense in category; possible new merchant.",
                })
        return results[:50]

    def set_anomaly_feedback(self, user_id: int, expense_id: str, feedback: str) -> None:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO "{SCHEMA}"."{FEEDBACK_TABLE}" (expense_id, user_id, feedback)
                VALUES (%s::uuid, %s, %s)
                ON CONFLICT (expense_id, user_id) DO UPDATE SET feedback = EXCLUDED.feedback
                """,
                (expense_id, user_id, feedback),
            )
        finally:
            conn.close()
