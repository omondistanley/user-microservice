"""
Budget data service: CRUD, list with filters, effective-at-date lookup.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = "budgets_db"
TABLE = "budget"


def _dict_row(row: Any) -> Optional[Dict]:
    if row is None:
        return None
    return dict(row)


class BudgetDataService:
    def __init__(self, context: Dict[str, Any]):
        self.context = context

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
