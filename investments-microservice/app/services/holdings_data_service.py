"""
Holdings data service: CRUD for investment positions.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = "investments_db"
TABLE = "holding"


def _dict_row(row: Any) -> Optional[Dict]:
    if row is None:
        return None
    return dict(row)


class HoldingsDataService:
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

    def insert_holding(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cols = [
            "user_id", "household_id", "symbol", "quantity", "avg_cost",
            "currency", "exchange", "notes", "created_at", "updated_at",
        ]
        keys = [k for k in cols if k in data]
        columns = ",".join(f'"{k}"' for k in keys)
        placeholders = ",".join(["%s"] * len(keys))
        vals = [data[k] for k in keys]
        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{TABLE}" ({columns}) '
                f"VALUES ({placeholders}) RETURNING holding_id, created_at, updated_at",
                vals,
            )
            row = cur.fetchone()
            conn.commit()
            if row:
                data["holding_id"] = row["holding_id"]
                data["created_at"] = row["created_at"]
                data["updated_at"] = row["updated_at"]
            return data
        finally:
            conn.close()

    def get_holding_by_id(self, holding_id: UUID, user_id: int) -> Optional[Dict]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE holding_id = %s AND user_id = %s',
                (holding_id, user_id),
            )
            row = cur.fetchone()
            return _dict_row(row)
        finally:
            conn.close()

    def list_holdings(
        self,
        user_id: int,
        household_id: Optional[UUID] = None,
        symbol: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict], int]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            where = ["user_id = %s"]
            params: List[Any] = [user_id]
            if household_id is not None:
                where.append("household_id IS NOT DISTINCT FROM %s")
                params.append(household_id)
            if symbol:
                where.append("symbol = %s")
                params.append(symbol.upper())
            where_sql = " AND ".join(where)
            cur.execute(
                f'SELECT COUNT(*) FROM "{SCHEMA}"."{TABLE}" WHERE {where_sql}',
                params,
            )
            total = cur.fetchone()["count"]
            offset = (page - 1) * page_size
            params.extend([page_size, offset])
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE {where_sql} '
                f'ORDER BY symbol ASC LIMIT %s OFFSET %s',
                params,
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows], total
        finally:
            conn.close()

    def update_holding(
        self,
        holding_id: UUID,
        user_id: int,
        updates: Dict[str, Any],
    ) -> Optional[Dict]:
        if not updates:
            return self.get_holding_by_id(holding_id, user_id)
        allowed = {"quantity", "avg_cost", "exchange", "notes", "updated_at"}
        updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if "updated_at" not in updates:
            updates["updated_at"] = datetime.now(timezone.utc)
        if not updates:
            return self.get_holding_by_id(holding_id, user_id)
        set_clause = ", ".join(f'"{k}" = %s' for k in updates)
        params = list(updates.values()) + [holding_id, user_id]
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" SET {set_clause} '
                f"WHERE holding_id = %s AND user_id = %s",
                params,
            )
            conn.commit()
            if cur.rowcount:
                return self.get_holding_by_id(holding_id, user_id)
            return None
        finally:
            conn.close()

    def delete_holding(self, holding_id: UUID, user_id: int) -> bool:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE holding_id = %s AND user_id = %s',
                (holding_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def purge_user_holdings(self, user_id: int) -> int:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s', (user_id,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def list_all_holdings_for_user(self, user_id: int) -> List[Dict]:
        """Return all holdings rows for a user for valuation/analytics."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s ORDER BY symbol ASC',
                (user_id,),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
