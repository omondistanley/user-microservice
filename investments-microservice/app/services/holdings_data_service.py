"""
Holdings data service: CRUD for investment positions.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2
from psycopg2 import errors as pg_errors
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
            "source", "external_id",
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
            if row:
                data["holding_id"] = row["holding_id"]
                data["created_at"] = row["created_at"]
                data["updated_at"] = row["updated_at"]
                # Create initial tax lot for cost basis (migration 008)
                try:
                    purchase_date = (data.get("created_at") or datetime.now(timezone.utc))
                    if hasattr(purchase_date, "date"):
                        purchase_date = purchase_date.date()
                    lot_source = data.get("source") or "manual"
                    cur.execute(
                        'INSERT INTO investments_db.tax_lot (holding_id, quantity, cost_per_share, purchase_date, source) '
                        'VALUES (%s, %s, %s, %s, %s)',
                        (
                            row["holding_id"],
                            data.get("quantity"),
                            data.get("avg_cost"),
                            purchase_date,
                            lot_source,
                        ),
                    )
                except Exception:
                    pass  # table may not exist yet
            conn.commit()
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

    def purge_user_holdings(self, user_id: int) -> Dict[str, int]:
        """
        GDPR / account deletion: remove all user-scoped investment data (not market-wide tables).
        Returns per-table delete counts for auditing.
        """
        conn = self._get_connection()
        summary: Dict[str, int] = {}

        def _del(label: str, sql: str, params: tuple) -> None:
            try:
                cur.execute(sql, params)
                summary[label] = int(cur.rowcount or 0)
            except pg_errors.UndefinedTable:
                summary[label] = 0

        try:
            cur = conn.cursor()
            # Order: dependent user rows first, holdings last (tax_lot cascades from holding).
            _del(
                "investments_db.transaction",
                f'DELETE FROM "{SCHEMA}"."transaction" WHERE user_id = %s',
                (user_id,),
            )
            _del(
                "investments_db.recommendation_run",
                f'DELETE FROM "{SCHEMA}".recommendation_run WHERE user_id = %s',
                (user_id,),
            )
            _del("recommendation_digest", "DELETE FROM recommendation_digest WHERE user_id = %s", (user_id,))
            _del(
                "portfolio_health_snapshot",
                "DELETE FROM portfolio_health_snapshot WHERE user_id = %s",
                (user_id,),
            )
            _del("watchlist", "DELETE FROM watchlist WHERE user_id = %s", (user_id,))
            _del("nudge_log", "DELETE FROM nudge_log WHERE user_id = %s", (user_id,))
            _del(
                "investments_db.portfolio_rebalance_session",
                f'DELETE FROM "{SCHEMA}".portfolio_rebalance_session WHERE user_id = %s',
                (user_id,),
            )
            _del(
                "investments_db.portfolio_snapshot",
                f'DELETE FROM "{SCHEMA}".portfolio_snapshot WHERE user_id = %s',
                (user_id,),
            )
            _del(
                "investments_db.risk_profile",
                f'DELETE FROM "{SCHEMA}".risk_profile WHERE user_id = %s',
                (user_id,),
            )
            _del(
                "investments_db.alpaca_connection",
                f'DELETE FROM "{SCHEMA}".alpaca_connection WHERE user_id = %s',
                (user_id,),
            )
            cur.execute(f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s', (user_id,))
            summary[f"{SCHEMA}.{TABLE}"] = int(cur.rowcount or 0)
            conn.commit()
            return summary
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_holdings_by_source(self, user_id: int, source: str) -> int:
        """Delete all holdings for user with the given source (e.g. 'alpaca'). Returns count deleted."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s AND source = %s',
                (user_id, source),
            )
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

    def list_distinct_symbols(self) -> List[str]:
        """Return distinct symbols across all holdings (for ETF sync job)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT DISTINCT symbol FROM "{SCHEMA}"."{TABLE}" ORDER BY symbol')
            return [r["symbol"] for r in cur.fetchall() if r.get("symbol")]
        finally:
            conn.close()

    def list_distinct_user_ids(self, limit: int = 5000) -> List[int]:
        """Return distinct user_ids with holdings for offline model training jobs."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT DISTINCT user_id FROM "{SCHEMA}"."{TABLE}" ORDER BY user_id ASC LIMIT %s',
                (limit,),
            )
            return [int(r["user_id"]) for r in cur.fetchall() if r.get("user_id") is not None]
        finally:
            conn.close()
