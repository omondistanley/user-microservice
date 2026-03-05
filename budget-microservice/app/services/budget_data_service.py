"""
Budget data service: CRUD, list with filters, effective-at-date lookup, and alert evaluation data access.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = "budgets_db"
TABLE = "budget"
ALERT_CONFIG_TABLE = "budget_alert_config"
ALERT_EVENT_TABLE = "budget_alert_event"


def _dict_row(row: Any) -> Optional[Dict]:
    if row is None:
        return None
    return dict(row)


class BudgetDataService:
    def __init__(self, context: Dict[str, Any], expense_context: Optional[Dict[str, Any]] = None):
        self.context = context
        self.expense_context = expense_context or context

    def _get_connection(self):
        conn = psycopg2.connect(
            host=self.context["host"],
            port=self.context["port"],
            user=self.context["user"],
            password=self.context["password"],
            dbname=self.context["dbname"],
            cursor_factory=RealDictCursor,
        )
        return conn

    def _get_expense_connection(self):
        conn = psycopg2.connect(
            host=self.expense_context["host"],
            port=self.expense_context["port"],
            user=self.expense_context["user"],
            password=self.expense_context["password"],
            dbname=self.expense_context["dbname"],
            cursor_factory=RealDictCursor,
        )
        return conn

    def _conn_autocommit(self):
        conn = self._get_connection()
        conn.autocommit = True
        return conn

    def insert_budget(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cols = [
            "user_id", "name", "category_code", "amount",
            "start_date", "end_date", "created_at", "updated_at",
        ]
        keys = [k for k in cols if k in data]
        columns = ",".join(f'"{k}"' for k in keys)
        placeholders = ",".join(["%s"] * len(keys))
        vals = [data[k] for k in keys]
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{TABLE}" ({columns}) '
                f"VALUES ({placeholders}) RETURNING budget_id, created_at, updated_at",
                vals,
            )
            row = cur.fetchone()
            if row:
                data["budget_id"] = row["budget_id"]
                data["created_at"] = row["created_at"]
                data["updated_at"] = row["updated_at"]
            return data
        finally:
            conn.close()

    def get_budget_by_id(self, budget_id: UUID, user_id: int) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE budget_id = %s AND user_id = %s',
                (str(budget_id), user_id),
            )
            row = cur.fetchone()
            return _dict_row(row)
        finally:
            conn.close()

    def list_budgets(
        self,
        user_id: int,
        category_code: Optional[int] = None,
        effective_date: Optional[str] = None,
        include_inactive: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict], int]:
        conditions = ["user_id = %s"]
        params: List[Any] = [user_id]
        if category_code is not None:
            conditions.append("category_code = %s")
            params.append(category_code)
        if effective_date and not include_inactive:
            conditions.append("start_date <= %s AND end_date >= %s")
            params.append(effective_date)
            params.append(effective_date)
        where = " AND ".join(conditions)
        offset = (page - 1) * page_size
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT COUNT(*) AS c FROM "{SCHEMA}"."{TABLE}" WHERE {where}',
                params,
            )
            total = cur.fetchone()["c"]
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE {where} '
                "ORDER BY start_date DESC, created_at DESC LIMIT %s OFFSET %s",
                params + [page_size, offset],
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows], total
        finally:
            conn.close()

    def get_effective_budget(
        self, user_id: int, category_code: int, effective_date: str
    ) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" '
                "WHERE user_id = %s AND category_code = %s AND start_date <= %s AND end_date >= %s "
                "ORDER BY start_date DESC LIMIT 1",
                (user_id, category_code, effective_date, effective_date),
            )
            row = cur.fetchone()
            return _dict_row(row)
        finally:
            conn.close()

    def update_budget(
        self, budget_id: UUID, user_id: int, data: Dict[str, Any]
    ) -> Optional[Dict]:
        allowed = {"name", "amount", "start_date", "end_date", "updated_at"}
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            return self.get_budget_by_id(budget_id, user_id)
        updates["updated_at"] = datetime.now(timezone.utc)
        sets = ", ".join(f'"{k}" = %s' for k in updates)
        params = list(updates.values()) + [str(budget_id), user_id]
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" SET {sets} '
                "WHERE budget_id = %s AND user_id = %s",
                params,
            )
            if cur.rowcount == 0:
                return None
            return self.get_budget_by_id(budget_id, user_id)
        finally:
            conn.close()

    def end_budget_period(
        self, budget_id: UUID, user_id: int, new_end_date: date
    ) -> bool:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" SET end_date = %s, updated_at = %s '
                "WHERE budget_id = %s AND user_id = %s",
                (new_end_date, datetime.now(timezone.utc), str(budget_id), user_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_budget(self, budget_id: UUID, user_id: int) -> bool:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE budget_id = %s AND user_id = %s',
                (str(budget_id), user_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    # --- Alert config and events ---
    def get_budget_alert_configs(self, user_id: int, budget_id: UUID) -> List[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT config_id, budget_id, threshold_percent, channel, is_active, created_at, updated_at '
                f'FROM "{SCHEMA}"."{ALERT_CONFIG_TABLE}" '
                "WHERE user_id = %s AND budget_id = %s::uuid "
                "ORDER BY threshold_percent ASC, created_at ASC",
                (user_id, str(budget_id)),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def replace_budget_alert_configs(
        self,
        user_id: int,
        budget_id: UUID,
        thresholds: List[Decimal],
        channel: str = "in_app",
    ) -> List[Dict]:
        normalized_thresholds: List[Decimal] = []
        seen: set[str] = set()
        for value in thresholds:
            v = Decimal(str(value)).quantize(Decimal("0.01"))
            if v <= 0:
                continue
            key = str(v)
            if key in seen:
                continue
            seen.add(key)
            normalized_thresholds.append(v)
        normalized_thresholds.sort()

        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{ALERT_CONFIG_TABLE}" '
                "WHERE user_id = %s AND budget_id = %s::uuid",
                (user_id, str(budget_id)),
            )
            created: List[Dict] = []
            now = datetime.now(timezone.utc)
            for threshold in normalized_thresholds:
                cur.execute(
                    f'INSERT INTO "{SCHEMA}"."{ALERT_CONFIG_TABLE}" '
                    "(user_id, budget_id, threshold_percent, channel, is_active, created_at, updated_at) "
                    "VALUES (%s, %s::uuid, %s, %s, true, %s, %s) "
                    "RETURNING config_id, budget_id, threshold_percent, channel, is_active, created_at, updated_at",
                    (user_id, str(budget_id), threshold, channel, now, now),
                )
                row = cur.fetchone()
                if row:
                    created.append(dict(row))
            conn.commit()
            return created
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_active_budget_alert_targets(
        self,
        as_of_date: date,
        user_id: Optional[int] = None,
    ) -> List[Dict]:
        conditions = [
            "c.is_active = true",
            "b.start_date <= %s",
            "b.end_date >= %s",
        ]
        params: List[Any] = [as_of_date, as_of_date]
        if user_id is not None:
            conditions.append("b.user_id = %s")
            params.append(user_id)
        where = " AND ".join(conditions)
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT
                    b.budget_id::text AS budget_id,
                    b.user_id,
                    b.category_code,
                    b.amount AS budget_amount,
                    b.start_date AS period_start,
                    b.end_date AS period_end,
                    c.threshold_percent,
                    c.channel
                FROM "{SCHEMA}"."{TABLE}" b
                JOIN "{SCHEMA}"."{ALERT_CONFIG_TABLE}" c
                  ON c.budget_id = b.budget_id AND c.user_id = b.user_id
                WHERE {where}
                ORDER BY b.user_id, b.budget_id, c.threshold_percent
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_spent_amount(
        self,
        user_id: int,
        category_code: int,
        period_start: date,
        period_end: date,
    ) -> Decimal:
        conn = self._get_expense_connection()
        conn.autocommit = True
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(SUM(e.amount), 0) AS total
                FROM expenses_db.expense e
                WHERE e.user_id = %s
                  AND e.category_code = %s
                  AND e.deleted_at IS NULL
                  AND e.date >= %s
                  AND e.date <= %s
                """,
                (user_id, category_code, period_start, period_end),
            )
            row = cur.fetchone()
            if not row or row.get("total") is None:
                return Decimal("0")
            return Decimal(str(row["total"]))
        finally:
            conn.close()

    def create_budget_alert_event(
        self,
        user_id: int,
        budget_id: str,
        period_start: date,
        period_end: date,
        threshold_percent: Decimal,
        spent_amount: Decimal,
        budget_amount: Decimal,
        channel: str,
        sent_at: Optional[datetime] = None,
    ) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO "{SCHEMA}"."{ALERT_EVENT_TABLE}" (
                    user_id, budget_id, period_start, period_end,
                    threshold_percent, spent_amount, budget_amount, channel, sent_at
                )
                VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, budget_id, period_start, period_end, threshold_percent, channel)
                DO NOTHING
                RETURNING event_id, user_id, budget_id, period_start, period_end,
                          threshold_percent, spent_amount, budget_amount, channel, sent_at
                """,
                (
                    user_id,
                    budget_id,
                    period_start,
                    period_end,
                    threshold_percent,
                    spent_amount,
                    budget_amount,
                    channel,
                    sent_at or datetime.now(timezone.utc),
                ),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def purge_user_budgets(self, user_id: int) -> Dict[str, int]:
        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            summary: Dict[str, int] = {}

            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{ALERT_EVENT_TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            summary["alert_events_deleted"] = cur.rowcount or 0

            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{ALERT_CONFIG_TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            summary["alert_configs_deleted"] = cur.rowcount or 0

            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            summary["budgets_deleted"] = cur.rowcount or 0

            conn.commit()
            return summary
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
