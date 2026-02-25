"""
Expense-specific data service: CRUD, list with filters, balance chain helpers.
Uses single-statement recalc for balance (Option 2).
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2
from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

SCHEMA = "expenses_db"
TABLE = "expense"
ORDER_COLS = "date, created_at, expense_id"
IDEMPOTENCY_TABLE = "idempotency"
IDEMPOTENCY_TTL_HOURS = 24


def _dict_row(row: Any) -> Optional[Dict]:
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = v
        elif hasattr(v, "isoformat"):
            d[k] = v
    return d


class ExpenseDataService:
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

    def get_connection(self, autocommit: bool = True):
        conn = self._get_connection()
        conn.autocommit = autocommit
        return conn

    def insert_expense(self, data: Dict[str, Any]) -> Dict[str, Any]:
        conn = self._conn_autocommit()
        try:
            return self._insert_expense_using_conn(conn, data)
        finally:
            conn.close()

    def _insert_expense_using_conn(self, conn: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        cols = [
            "user_id", "category_code", "category_name", "amount", "date",
            "currency", "budget_category_id", "description", "balance_after",
            "created_at", "updated_at",
            "source", "plaid_transaction_id",
        ]
        keys = [k for k in cols if k in data]
        columns = ",".join(f'"{k}"' for k in keys)
        placeholders = ",".join(["%s"] * len(keys))
        vals = [data[k] for k in keys]
        sql = (
            f'INSERT INTO "{SCHEMA}"."{TABLE}" ({columns}) '
            f"VALUES ({placeholders}) RETURNING expense_id, created_at, updated_at"
        )
        cur = conn.cursor()
        cur.execute(sql, vals)
        row = cur.fetchone()
        if row:
            data["expense_id"] = row["expense_id"]
            data["created_at"] = row["created_at"]
            data["updated_at"] = row["updated_at"]
        return data

    def get_expense_by_id(self, expense_id: UUID, user_id: int) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE expense_id = %s AND user_id = %s',
                (str(expense_id), user_id),
            )
            row = cur.fetchone()
            return _dict_row(row)
        finally:
            conn.close()

    def get_expense_by_id_any(self, expense_id: UUID) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE expense_id = %s',
                (str(expense_id),),
            )
            row = cur.fetchone()
            return _dict_row(row)
        finally:
            conn.close()

    def get_expense_by_plaid_transaction_id(
        self, user_id: int, plaid_transaction_id: str
    ) -> Optional[Dict]:
        if not plaid_transaction_id:
            return None
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s AND plaid_transaction_id = %s AND deleted_at IS NULL',
                (user_id, plaid_transaction_id),
            )
            row = cur.fetchone()
            return _dict_row(row)
        finally:
            conn.close()

    def list_expenses(
        self,
        user_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        category_code: Optional[int] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Dict], int]:
        conditions = ['user_id = %s', 'deleted_at IS NULL']
        params: List[Any] = [user_id]
        if date_from:
            conditions.append('date >= %s')
            params.append(date_from)
        if date_to:
            conditions.append('date <= %s')
            params.append(date_to)
        if category_code is not None:
            conditions.append('category_code = %s')
            params.append(category_code)
        if min_amount is not None:
            conditions.append('amount >= %s')
            params.append(min_amount)
        if max_amount is not None:
            conditions.append('amount <= %s')
            params.append(max_amount)
        where = " AND ".join(conditions)
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            count_sql = f'SELECT COUNT(*) AS c FROM "{SCHEMA}"."{TABLE}" WHERE {where}'
            cur.execute(count_sql, params)
            total = cur.fetchone()["c"]
            list_sql = (
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE {where} '
                f"ORDER BY date DESC, created_at DESC, expense_id DESC LIMIT %s OFFSET %s"
            )
            cur.execute(list_sql, params + [limit, offset])
            rows = cur.fetchall()
            return [dict(r) for r in rows], total
        finally:
            conn.close()

    def update_expense(
        self, expense_id: UUID, user_id: int, data: Dict[str, Any]
    ) -> Optional[Dict]:
        allowed = {
            "amount", "date", "category_code", "category_name", "currency",
            "budget_category_id", "description", "updated_at",
        }
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            return self.get_expense_by_id(expense_id, user_id)
        sets = ", ".join(f'"{k}" = %s' for k in updates)
        params = list(updates.values()) + [str(expense_id), user_id]
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" SET {sets} '
                "WHERE expense_id = %s AND user_id = %s",
                params,
            )
            if cur.rowcount == 0:
                return None
            return self.get_expense_by_id(expense_id, user_id)
        finally:
            conn.close()

    def soft_delete(self, expense_id: UUID, user_id: int) -> bool:
        from datetime import datetime, timezone
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" SET deleted_at = %s, updated_at = %s '
                "WHERE expense_id = %s AND user_id = %s",
                (datetime.now(timezone.utc), datetime.now(timezone.utc), str(expense_id), user_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_previous_expense(
        self,
        user_id: int,
        date_val: str,
        created_at: Any,
        expense_id: UUID,
        conn: Any = None,
    ) -> Optional[Dict]:
        """Previous expense in order (date DESC, created_at DESC, expense_id DESC) for balance chain."""
        own_conn = conn is None
        if own_conn:
            conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT * FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s AND deleted_at IS NULL
                  AND (date, created_at, expense_id) < (%s, %s, %s::uuid)
                ORDER BY date DESC, created_at DESC, expense_id DESC
                LIMIT 1
                """,
                (user_id, date_val, created_at, str(expense_id)),
            )
            row = cur.fetchone()
            return _dict_row(row)
        finally:
            if own_conn and conn:
                conn.close()

    def recalc_balance_after(
        self,
        conn: Any,
        user_id: int,
        pivot_date: str,
        pivot_created_at: Any,
        pivot_expense_id: str,
        balance_before_pivot: Decimal,
    ) -> None:
        """
        Single-statement recalc: set balance_after for all rows at or after pivot.
        Run inside a transaction with conn (no autocommit).
        """
        cur = conn.cursor()
        cur.execute(
            f"""
            WITH ordered AS (
                SELECT expense_id, amount,
                       row_number() OVER (ORDER BY {ORDER_COLS}) AS rn
                FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s AND deleted_at IS NULL
                  AND (date, created_at, expense_id) >= (%s, %s, %s::uuid)
            ),
            with_balance AS (
                SELECT expense_id,
                       %s + sum(amount) OVER (ORDER BY rn) AS balance_after
                FROM ordered
            )
            UPDATE "{SCHEMA}"."{TABLE}" e
            SET balance_after = w.balance_after, updated_at = now()
            FROM with_balance w
            WHERE e.expense_id = w.expense_id
            """,
            (user_id, pivot_date, pivot_created_at, pivot_expense_id, balance_before_pivot),
        )

    def get_current_balance(
        self, user_id: int, as_of_date: Optional[str] = None
    ) -> Decimal:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            if as_of_date:
                cur.execute(
                    f"""
                    SELECT balance_after FROM "{SCHEMA}"."{TABLE}"
                    WHERE user_id = %s AND deleted_at IS NULL AND date <= %s
                    ORDER BY date DESC, created_at DESC, expense_id DESC
                    LIMIT 1
                    """,
                    (user_id, as_of_date),
                )
            else:
                cur.execute(
                    f"""
                    SELECT balance_after FROM "{SCHEMA}"."{TABLE}"
                    WHERE user_id = %s AND deleted_at IS NULL
                    ORDER BY date DESC, created_at DESC, expense_id DESC
                    LIMIT 1
                    """,
                    (user_id,),
                )
            row = cur.fetchone()
            if row and row.get("balance_after") is not None:
                return row["balance_after"]
            return Decimal("0")
        finally:
            conn.close()

    def get_balance_history(
        self,
        user_id: int,
        date_from: str,
        date_to: str,
        group_by: str = "week",
    ) -> List[Dict[str, Any]]:
        """Return list of { date: "YYYY-MM-DD", balance: Decimal } in chronological order."""
        from datetime import datetime, timedelta

        try:
            start = datetime.strptime(date_from[:10], "%Y-%m-%d").date()
            end = datetime.strptime(date_to[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return []
        if start > end:
            return []

        dates: List[str] = []
        if group_by == "day":
            d = start
            while d <= end:
                dates.append(d.isoformat())
                d += timedelta(days=1)
        else:
            d = start
            while d <= end:
                dates.append(d.isoformat())
                d += timedelta(weeks=1)

        out = []
        for d in dates:
            bal = self.get_current_balance(user_id, d)
            out.append({"date": d, "balance": bal})
        return out

    def acquire_user_lock(self, conn: Any, user_id: int) -> None:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(user_id),))

    def update_expense_balance_after(
        self, conn: Any, expense_id: str, user_id: int, balance_after: Decimal
    ) -> None:
        cur = conn.cursor()
        cur.execute(
            f'UPDATE "{SCHEMA}"."{TABLE}" SET balance_after = %s, updated_at = now() '
            "WHERE expense_id = %s AND user_id = %s",
            (balance_after, expense_id, user_id),
        )

    def get_categories(self) -> List[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT category_code, name FROM "{SCHEMA}".category ORDER BY category_code'
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def insert_category(self, name: str) -> Optional[Dict]:
        """Create a new category with next available category_code. Returns created row or None on duplicate name."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT COALESCE(MAX(category_code), 0) + 1 AS next_code FROM "{SCHEMA}".category'
            )
            row = cur.fetchone()
            next_code = row["next_code"] if row else 1
            cur.execute(
                f'INSERT INTO "{SCHEMA}".category (category_code, name) VALUES (%s, %s) RETURNING category_code, name',
                (next_code, name.strip()),
            )
            created = cur.fetchone()
            return _dict_row(created) if created else None
        except Exception:
            raise
        finally:
            conn.close()

    def resolve_category(self, category_code: Optional[int], category_name: Optional[str]) -> Optional[Tuple[int, str]]:
        """Return (category_code, name) from master. Accept either code or name."""
        cats = {c["category_code"]: c["name"] for c in self.get_categories()}
        name_to_code = {c["name"].lower(): c["category_code"] for c in self.get_categories()}
        if category_code is not None and category_code in cats:
            return (category_code, cats[category_code])
        if category_name is not None and category_name.strip():
            key = category_name.strip().lower()
            if key in name_to_code:
                code = name_to_code[key]
                return (code, cats[code])
        return None

    # --- Receipts (metadata; file storage is external) ---
    RECEIPT_TABLE = "receipt"

    def insert_receipt(self, expense_id: str, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        data["expense_id"] = expense_id
        data["user_id"] = user_id
        cols = ["expense_id", "user_id", "file_name", "content_type", "file_size_bytes", "storage_key", "file_bytes"]
        keys = [k for k in cols if k in data]
        columns = ",".join(f'"{k}"' for k in keys)
        placeholders = ",".join(["%s"] * len(keys))
        vals = [data[k] for k in keys]
        sql = (
            f'INSERT INTO "{SCHEMA}"."{RECEIPT_TABLE}" ({columns}) '
            f"VALUES ({placeholders}) RETURNING receipt_id, uploaded_at"
        )
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(sql, vals)
            row = cur.fetchone()
            if row:
                data["receipt_id"] = row["receipt_id"]
                data["uploaded_at"] = row["uploaded_at"]
            return data
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            conn.close()

    def get_receipt_bytes(self, receipt_id: str, user_id: int) -> Optional[bytes]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT r.file_bytes FROM "{SCHEMA}"."{RECEIPT_TABLE}" r '
                f'JOIN "{SCHEMA}"."{TABLE}" e ON e.expense_id = r.expense_id '
                "WHERE r.receipt_id = %s AND e.user_id = %s",
                (receipt_id, user_id),
            )
            row = cur.fetchone()
            if row and row.get("file_bytes") is not None:
                return bytes(row["file_bytes"])
            return None
        finally:
            conn.close()

    def get_receipts_by_expense(self, expense_id: str, user_id: int) -> List[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT r.* FROM "{SCHEMA}"."{RECEIPT_TABLE}" r '
                f'JOIN "{SCHEMA}"."{TABLE}" e ON e.expense_id = r.expense_id '
                "WHERE r.expense_id = %s AND e.user_id = %s ORDER BY r.uploaded_at",
                (expense_id, user_id),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_receipt_by_id(self, receipt_id: str, user_id: int) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT r.* FROM "{SCHEMA}"."{RECEIPT_TABLE}" r '
                f'JOIN "{SCHEMA}"."{TABLE}" e ON e.expense_id = r.expense_id '
                "WHERE r.receipt_id = %s AND e.user_id = %s",
                (receipt_id, user_id),
            )
            row = cur.fetchone()
            return _dict_row(row)
        finally:
            conn.close()

    def delete_receipt(self, receipt_id: str, user_id: int) -> bool:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{RECEIPT_TABLE}" r '
                f'USING "{SCHEMA}"."{TABLE}" e '
                "WHERE r.expense_id = e.expense_id AND e.user_id = %s AND r.receipt_id = %s",
                (user_id, receipt_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_expense_summary(
        self,
        user_id: int,
        group_by: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict]:
        """group_by: 'category' | 'month'. Returns list of {group_key, label, total_amount, count}."""
        conditions = ["user_id = %s", "deleted_at IS NULL"]
        params: List[Any] = [user_id]
        if date_from:
            conditions.append("date >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("date <= %s")
            params.append(date_to)
        where = " AND ".join(conditions)
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            if group_by == "category":
                cur.execute(
                    f"""
                    SELECT e.category_code AS group_key, e.category_name AS label,
                           SUM(e.amount) AS total_amount, COUNT(*) AS count
                    FROM "{SCHEMA}"."{TABLE}" e
                    WHERE {where}
                    GROUP BY e.category_code, e.category_name
                    ORDER BY total_amount DESC
                    """,
                    params,
                )
                rows = cur.fetchall()
                return [
                    {"group_key": str(r["group_key"]), "label": r["label"], "total_amount": r["total_amount"], "count": r["count"]}
                    for r in rows
                ]
            elif group_by == "month":
                cur.execute(
                    f"""
                    SELECT to_char(e.date, 'YYYY-MM') AS group_key,
                           to_char(e.date, 'YYYY-MM') AS label,
                           SUM(e.amount) AS total_amount, COUNT(*) AS count
                    FROM "{SCHEMA}"."{TABLE}" e
                    WHERE {where}
                    GROUP BY to_char(e.date, 'YYYY-MM')
                    ORDER BY group_key DESC
                    """,
                    params,
                )
                return [dict(r) for r in cur.fetchall()]
            return []
        finally:
            conn.close()

    def get_idempotent_expense_id(self, user_id: int, idempotency_key: str) -> Optional[str]:
        """Return expense_id if key was used within TTL, else None."""
        from datetime import datetime, timezone, timedelta
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=IDEMPOTENCY_TTL_HOURS)).isoformat()
            cur.execute(
                f'SELECT expense_id, created_at FROM "{SCHEMA}"."{IDEMPOTENCY_TABLE}" '
                "WHERE user_id = %s AND idempotency_key = %s AND created_at > %s",
                (user_id, idempotency_key, cutoff),
            )
            row = cur.fetchone()
            if row:
                return str(row["expense_id"])
            return None
        finally:
            conn.close()

    def set_idempotency(self, user_id: int, idempotency_key: str, expense_id: str) -> None:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{IDEMPOTENCY_TABLE}" (user_id, idempotency_key, expense_id) '
                "VALUES (%s, %s, %s::uuid) ON CONFLICT (user_id, idempotency_key) DO NOTHING",
                (user_id, idempotency_key, expense_id),
            )
        finally:
            conn.close()
