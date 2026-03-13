"""
Phase 4: Savings goals and contributions data access.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2
from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

SCHEMA = "expenses_db"
GOAL_TABLE = "savings_goal"
CONTRIBUTION_TABLE = "goal_contribution"


def _dict_row(row: Any) -> Optional[Dict]:
    if row is None:
        return None
    return dict(row)


class GoalDataService:
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

    def create_goal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cols = ["user_id", "household_id", "name", "target_amount", "target_currency", "target_date", "start_amount", "is_active", "created_at", "updated_at"]
        keys = [k for k in cols if k in data]
        columns = ",".join(f'"{k}"' for k in keys)
        placeholders = ",".join(["%s"] * len(keys))
        vals = [data[k] for k in keys]
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{GOAL_TABLE}" ({columns}) VALUES ({placeholders}) '
                "RETURNING goal_id, user_id, household_id, name, target_amount, target_currency, target_date, start_amount, is_active, created_at, updated_at",
                vals,
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_goal_by_id(self, goal_id: UUID, user_id: int) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{GOAL_TABLE}" WHERE goal_id = %s AND user_id = %s',
                (str(goal_id), user_id),
            )
            return _dict_row(cur.fetchone())
        finally:
            conn.close()

    def list_goals(
        self,
        user_id: int,
        household_id: Optional[str] = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict], int]:
        conditions = ["user_id = %s"]
        params: List[Any] = [user_id]
        if household_id is not None:
            conditions.append("household_id IS NOT DISTINCT FROM %s")
            params.append(household_id)
        if active_only:
            conditions.append("is_active = TRUE")
        where = " AND ".join(conditions)
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT COUNT(*) AS c FROM "{SCHEMA}"."{GOAL_TABLE}" WHERE {where}', params)
            total = cur.fetchone()["c"]
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{GOAL_TABLE}" WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s',
                params + [limit, offset],
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows], total
        finally:
            conn.close()

    def update_goal(self, goal_id: UUID, user_id: int, data: Dict[str, Any]) -> Optional[Dict]:
        allowed = {"name", "target_amount", "target_currency", "target_date", "start_amount", "is_active", "updated_at"}
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if "updated_at" not in updates:
            updates["updated_at"] = datetime.now(timezone.utc)
        if not updates:
            return self.get_goal_by_id(goal_id, user_id)
        sets = ", ".join(f'"{k}" = %s' for k in updates)
        params = list(updates.values()) + [str(goal_id), user_id]
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{GOAL_TABLE}" SET {sets} WHERE goal_id = %s AND user_id = %s',
                params,
            )
            if cur.rowcount == 0:
                return None
            return self.get_goal_by_id(goal_id, user_id)
        finally:
            conn.close()

    def delete_goal(self, goal_id: UUID, user_id: int) -> bool:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{GOAL_TABLE}" WHERE goal_id = %s AND user_id = %s',
                (str(goal_id), user_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def add_contribution(self, goal_id: UUID, user_id: int, amount: Decimal, contribution_date: date, source: str = "manual") -> Dict[str, Any]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{CONTRIBUTION_TABLE}" (goal_id, user_id, amount, contribution_date, source) '
                "VALUES (%s, %s, %s, %s, %s) RETURNING contribution_id, goal_id, user_id, amount, contribution_date, source, created_at",
                (str(goal_id), user_id, amount, contribution_date, source),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_contributions_total(self, goal_id: UUID) -> Decimal:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT COALESCE(SUM(amount), 0) AS total FROM "{SCHEMA}"."{CONTRIBUTION_TABLE}" WHERE goal_id = %s',
                (str(goal_id),),
            )
            row = cur.fetchone()
            return Decimal(str(row["total"])) if row else Decimal("0")
        finally:
            conn.close()

    def get_progress(self, goal_id: UUID, user_id: int) -> Optional[Dict]:
        goal = self.get_goal_by_id(goal_id, user_id)
        if not goal:
            return None
        total_contrib = self.get_contributions_total(goal_id)
        start = Decimal(str(goal.get("start_amount", 0)))
        current = start + total_contrib
        target = Decimal(str(goal["target_amount"]))
        remaining = max(Decimal("0"), target - current)
        percent = (float(current) / float(target) * 100) if target else Decimal("0")
        target_date = goal.get("target_date")
        days_remaining = None
        if target_date:
            today = date.today()
            if isinstance(target_date, str):
                target_date = date.fromisoformat(target_date)
            days_remaining = max(0, (target_date - today).days)
        return {
            "goal_id": str(goal_id),
            "current_amount": float(current),
            "target_amount": float(target),
            "remaining_amount": float(remaining),
            "percent_complete": round(percent, 2),
            "days_remaining": days_remaining,
            "start_amount": float(start),
            "contributions_total": float(total_contrib),
        }
