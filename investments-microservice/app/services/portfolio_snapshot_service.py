from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = "investments_db"
TABLE = "portfolio_snapshot"


class PortfolioSnapshotDataService:
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

    def insert_snapshot(
        self,
        user_id: int,
        snapshot_date: date,
        total_value: Decimal,
        total_cost_basis: Decimal,
        unrealized_pl: Decimal,
        realized_pl: Decimal = Decimal("0"),
    ) -> Dict[str, Any]:
        conn = self._get_connection()
        conn.autocommit = False
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{TABLE}" '
                f"(user_id, snapshot_date, total_value, total_cost_basis, unrealized_pl, realized_pl) "
                f"VALUES (%s, %s, %s, %s, %s, %s) "
                f"RETURNING snapshot_id, created_at",
                (
                    user_id,
                    snapshot_date,
                    total_value,
                    total_cost_basis,
                    unrealized_pl,
                    realized_pl,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_latest_snapshot(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" '
                f"WHERE user_id = %s ORDER BY snapshot_date DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_snapshots(
        self,
        user_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            where = ['user_id = %s']
            params: List[Any] = [user_id]
            if date_from:
                where.append("snapshot_date >= %s")
                params.append(date_from)
            if date_to:
                where.append("snapshot_date <= %s")
                params.append(date_to)
            where_sql = " AND ".join(where)
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" '
                f"WHERE {where_sql} ORDER BY snapshot_date ASC",
                params,
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

