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
ROUND_UP_CONFIG_TABLE = "round_up_config"


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
        months_left = None
        suggested_monthly = None
        on_track = None
        if target_date:
            today = date.today()
            if isinstance(target_date, str):
                target_date = date.fromisoformat(target_date)
            days_remaining = max(0, (target_date - today).days)
            if days_remaining > 0 and remaining > 0:
                months_left = max(1, days_remaining / 30.0)
                suggested_monthly = float(remaining) / months_left
        if suggested_monthly is not None and suggested_monthly > 0:
            recent_total = self._get_contributions_total_since(goal_id, days=30)
            on_track = float(recent_total) >= suggested_monthly or remaining <= 0
        elif remaining <= 0:
            on_track = True
        return {
            "goal_id": str(goal_id),
            "current_amount": float(current),
            "target_amount": float(target),
            "remaining_amount": float(remaining),
            "percent_complete": round(percent, 2),
            "days_remaining": days_remaining,
            "start_amount": float(start),
            "contributions_total": float(total_contrib),
            "suggested_monthly": round(suggested_monthly, 2) if suggested_monthly is not None else None,
            "on_track": on_track,
        }

    def _get_contributions_total_since(self, goal_id: UUID, days: int = 30) -> Decimal:
        """Sum contributions in the last `days` days for this goal."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT COALESCE(SUM(amount), 0) AS total FROM \"{SCHEMA}\".\"{CONTRIBUTION_TABLE}\" "
                "WHERE goal_id = %s AND contribution_date >= CURRENT_DATE - INTERVAL '1 day' * %s",
                (str(goal_id), days),
            )
            row = cur.fetchone()
            return Decimal(str(row["total"])) if row else Decimal("0")
        finally:
            conn.close()

    def list_contributions_for_goal(self, goal_id: UUID, user_id: int) -> List[Dict]:
        """List contributions for a goal (goal must belong to user). Returns list with user_id per contribution."""
        goal = self.get_goal_by_id(goal_id, user_id)
        if not goal:
            return []
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT contribution_id, goal_id, user_id, amount, contribution_date, source, created_at '
                f'FROM "{SCHEMA}"."{CONTRIBUTION_TABLE}" WHERE goal_id = %s ORDER BY contribution_date DESC, created_at DESC',
                (str(goal_id),),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def list_round_up_configs(self, user_id: int, active_only: bool = True) -> List[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            where = "user_id = %s"
            params: List[Any] = [user_id]
            if active_only:
                where += " AND is_active = TRUE"
            cur.execute(
                f'SELECT id, user_id, goal_id, round_to, is_active, last_processed_at, created_at, updated_at '
                f'FROM "{SCHEMA}"."{ROUND_UP_CONFIG_TABLE}" WHERE {where}',
                params,
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_round_up_config(self, config_id: str, user_id: int) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{ROUND_UP_CONFIG_TABLE}" WHERE id = %s::uuid AND user_id = %s',
                (config_id, user_id),
            )
            return _dict_row(cur.fetchone())
        finally:
            conn.close()

    def get_round_up_config_by_goal(self, goal_id: UUID, user_id: int) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{ROUND_UP_CONFIG_TABLE}" WHERE goal_id = %s AND user_id = %s',
                (str(goal_id), user_id),
            )
            return _dict_row(cur.fetchone())
        finally:
            conn.close()

    def create_round_up_config(self, user_id: int, goal_id: UUID, round_to: Decimal = Decimal("1")) -> Dict:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{ROUND_UP_CONFIG_TABLE}" (user_id, goal_id, round_to, is_active, created_at, updated_at) '
                "VALUES (%s, %s, %s, TRUE, now(), now()) "
                "ON CONFLICT (user_id, goal_id) DO UPDATE SET round_to = EXCLUDED.round_to, is_active = TRUE, updated_at = now() "
                "RETURNING id, user_id, goal_id, round_to, is_active, last_processed_at, created_at, updated_at",
                (user_id, str(goal_id), round_to),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def update_round_up_config(self, config_id: str, user_id: int, is_active: Optional[bool] = None, round_to: Optional[Decimal] = None) -> Optional[Dict]:
        updates = []
        params: List[Any] = []
        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)
        if round_to is not None:
            updates.append("round_to = %s")
            params.append(round_to)
        if not updates:
            return self.get_round_up_config(config_id, user_id)
        updates.append("updated_at = now()")
        params.extend([config_id, user_id])
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{ROUND_UP_CONFIG_TABLE}" SET {", ".join(updates)} WHERE id = %s::uuid AND user_id = %s',
                params,
            )
            return self.get_round_up_config(config_id, user_id) if cur.rowcount else None
        finally:
            conn.close()

    def delete_round_up_config(self, config_id: str, user_id: int) -> bool:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(f'DELETE FROM "{SCHEMA}"."{ROUND_UP_CONFIG_TABLE}" WHERE id = %s::uuid AND user_id = %s', (config_id, user_id))
            return cur.rowcount > 0
        finally:
            conn.close()

    def mark_round_up_processed(self, config_id: str, user_id: int, when: Optional[datetime] = None) -> None:
        ts = when or datetime.now(timezone.utc)
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{ROUND_UP_CONFIG_TABLE}" SET last_processed_at = %s, updated_at = %s WHERE id = %s::uuid AND user_id = %s',
                (ts, ts, config_id, user_id),
            )
        finally:
            conn.close()

    def list_all_active_round_up_configs(self) -> List[Dict]:
        """Return all active round-up configs (for job)."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT id, user_id, goal_id, round_to, is_active, last_processed_at FROM "{SCHEMA}"."{ROUND_UP_CONFIG_TABLE}" WHERE is_active = TRUE'
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
