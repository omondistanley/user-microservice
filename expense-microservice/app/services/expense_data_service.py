"""
Expense-specific data service: CRUD, list with filters, balance chain helpers.
Uses single-statement recalc for balance (Option 2).
"""
import calendar
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2
from fastapi import HTTPException
from psycopg2.extras import RealDictCursor, Json

SCHEMA = "expenses_db"
TABLE = "expense"
ORDER_COLS = "date, created_at, expense_id"
IDEMPOTENCY_TABLE = "idempotency"
IDEMPOTENCY_TTL_HOURS = 24
INCOME_TABLE = "income"
RECURRING_TABLE = "recurring_expense"
TAG_TABLE = "tag"
EXPENSE_TAG_TABLE = "expense_tag"
EXCHANGE_RATE_TABLE = "exchange_rate"


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


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _advance_due_date(current_due: date, recurrence_rule: str) -> date:
    if recurrence_rule == "weekly":
        return current_due + timedelta(days=7)
    if recurrence_rule == "monthly":
        return _add_months(current_due, 1)
    if recurrence_rule == "yearly":
        return _add_months(current_due, 12)
    raise ValueError(f"Unsupported recurrence_rule: {recurrence_rule}")


def _slugify_tag_name(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not base:
        base = "tag"
    return base[:80]


def _normalize_currency(value: Optional[str], fallback: str = "USD") -> str:
    if not value:
        return fallback
    cur = str(value).strip().upper()
    if len(cur) != 3:
        return fallback
    return cur


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
            "source", "plaid_transaction_id", "teller_transaction_id",
            "household_id",
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

    def get_expense_by_teller_transaction_id(
        self, user_id: int, teller_transaction_id: str
    ) -> "Optional[Dict]":
        if not teller_transaction_id:
            return None
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s AND teller_transaction_id = %s AND deleted_at IS NULL',
                (user_id, teller_transaction_id),
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
        tag_id: Optional[str] = None,
        tag_slug: Optional[str] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        household_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Dict], int]:
        conditions = ['e.user_id = %s', 'e.deleted_at IS NULL']
        params: List[Any] = [user_id]
        if household_id is not None:
            conditions.append('e.household_id IS NOT DISTINCT FROM %s')
            params.append(household_id)
        if date_from:
            conditions.append('e.date >= %s')
            params.append(date_from)
        if date_to:
            conditions.append('e.date <= %s')
            params.append(date_to)
        if category_code is not None:
            conditions.append('e.category_code = %s')
            params.append(category_code)
        if tag_id:
            conditions.append(
                f"""
                EXISTS (
                    SELECT 1 FROM "{SCHEMA}"."{EXPENSE_TAG_TABLE}" et
                    WHERE et.expense_id = e.expense_id
                      AND et.tag_id = %s::uuid
                )
                """
            )
            params.append(tag_id)
        if tag_slug:
            conditions.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM "{SCHEMA}"."{EXPENSE_TAG_TABLE}" et
                    JOIN "{SCHEMA}"."{TAG_TABLE}" t ON t.tag_id = et.tag_id
                    WHERE et.expense_id = e.expense_id
                      AND t.user_id = e.user_id
                      AND t.slug = %s
                )
                """
            )
            params.append(tag_slug.strip().lower())
        if min_amount is not None:
            conditions.append('e.amount >= %s')
            params.append(min_amount)
        if max_amount is not None:
            conditions.append('e.amount <= %s')
            params.append(max_amount)
        where = " AND ".join(conditions)
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            count_sql = f'SELECT COUNT(*) AS c FROM "{SCHEMA}"."{TABLE}" e WHERE {where}'
            cur.execute(count_sql, params)
            total = cur.fetchone()["c"]
            list_sql = (
                f'SELECT e.* FROM "{SCHEMA}"."{TABLE}" e WHERE {where} '
                "ORDER BY e.date DESC, e.created_at DESC, e.expense_id DESC LIMIT %s OFFSET %s"
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

    # --- Tags ---
    def list_tags(self, user_id: int) -> List[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT tag_id, user_id, name, slug, created_at, updated_at '
                f'FROM "{SCHEMA}"."{TAG_TABLE}" '
                "WHERE user_id = %s "
                "ORDER BY lower(name), created_at ASC",
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _generate_unique_slug(
        self,
        conn: Any,
        user_id: int,
        name: str,
    ) -> str:
        base = _slugify_tag_name(name)
        candidate = base
        suffix = 2
        while True:
            cur = conn.cursor()
            cur.execute(
                f'SELECT 1 FROM "{SCHEMA}"."{TAG_TABLE}" '
                "WHERE user_id = %s AND slug = %s LIMIT 1",
                (user_id, candidate),
            )
            if cur.fetchone() is None:
                return candidate
            candidate = f"{base}-{suffix}"[:80]
            suffix += 1

    def _create_tag_using_conn(self, conn: Any, user_id: int, name: str) -> Dict[str, Any]:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValueError("Tag name is required")
        if len(cleaned) > 64:
            raise ValueError("Tag name must be 64 characters or fewer")

        cur = conn.cursor()
        cur.execute(
            f'SELECT tag_id, user_id, name, slug, created_at, updated_at '
            f'FROM "{SCHEMA}"."{TAG_TABLE}" '
            "WHERE user_id = %s AND lower(name) = lower(%s)",
            (user_id, cleaned),
        )
        existing = cur.fetchone()
        if existing:
            raise PermissionError("Tag already exists")

        slug = self._generate_unique_slug(conn, user_id, cleaned)
        now = datetime.now(timezone.utc)
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{TAG_TABLE}" '
            "(user_id, name, slug, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s) "
            "RETURNING tag_id, user_id, name, slug, created_at, updated_at",
            (user_id, cleaned, slug, now, now),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Failed to create tag")
        return dict(row)

    def create_tag(self, user_id: int, name: str) -> Dict:
        conn = self.get_connection(autocommit=False)
        try:
            created = self._create_tag_using_conn(conn, user_id, name)
            conn.commit()
            return created
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_tag(self, user_id: int, tag_id: str) -> bool:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TAG_TABLE}" '
                "WHERE user_id = %s AND tag_id = %s::uuid",
                (user_id, tag_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_tags_for_expense(self, expense_id: str, user_id: int) -> List[Dict]:
        tags_by_expense = self.get_tags_for_expense_ids([expense_id], user_id)
        return tags_by_expense.get(str(expense_id), [])

    def get_tags_for_expense_ids(self, expense_ids: List[str], user_id: int) -> Dict[str, List[Dict]]:
        if not expense_ids:
            return {}
        conn = self._conn_autocommit()
        out: Dict[str, List[Dict]] = {str(eid): [] for eid in expense_ids}
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT et.expense_id::text AS expense_id,
                       t.tag_id, t.user_id, t.name, t.slug, t.created_at, t.updated_at
                FROM "{SCHEMA}"."{EXPENSE_TAG_TABLE}" et
                JOIN "{SCHEMA}"."{TAG_TABLE}" t ON t.tag_id = et.tag_id
                WHERE et.expense_id = ANY(%s::uuid[]) AND t.user_id = %s
                ORDER BY lower(t.name), t.created_at ASC
                """,
                (expense_ids, user_id),
            )
            for row in cur.fetchall():
                expense_key = str(row["expense_id"])
                out.setdefault(expense_key, []).append(
                    {
                        "tag_id": row["tag_id"],
                        "user_id": row["user_id"],
                        "name": row["name"],
                        "slug": row["slug"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                )
            return out
        finally:
            conn.close()

    def _resolve_tag_rows(
        self,
        conn: Any,
        user_id: int,
        tag_ids: Optional[List[str]] = None,
        tag_names: Optional[List[str]] = None,
    ) -> List[Dict]:
        resolved: List[Dict] = []
        seen_tag_ids: set[str] = set()

        if tag_ids:
            cur = conn.cursor()
            cur.execute(
                f'SELECT tag_id, user_id, name, slug, created_at, updated_at '
                f'FROM "{SCHEMA}"."{TAG_TABLE}" '
                "WHERE user_id = %s AND tag_id = ANY(%s::uuid[])",
                (user_id, tag_ids),
            )
            rows = [dict(r) for r in cur.fetchall()]
            if len(rows) != len(set(str(tid) for tid in tag_ids)):
                raise HTTPException(status_code=400, detail="One or more tag_ids are invalid")
            for row in rows:
                key = str(row["tag_id"])
                if key in seen_tag_ids:
                    continue
                seen_tag_ids.add(key)
                resolved.append(row)

        if tag_names:
            normalized_names: List[str] = []
            seen_names: set[str] = set()
            for name in tag_names:
                cleaned = (name or "").strip()
                if not cleaned:
                    continue
                lower = cleaned.lower()
                if lower in seen_names:
                    continue
                seen_names.add(lower)
                normalized_names.append(cleaned)
            for cleaned in normalized_names:
                cur = conn.cursor()
                cur.execute(
                    f'SELECT tag_id, user_id, name, slug, created_at, updated_at '
                    f'FROM "{SCHEMA}"."{TAG_TABLE}" '
                    "WHERE user_id = %s AND lower(name) = lower(%s)",
                    (user_id, cleaned),
                )
                row = cur.fetchone()
                if row:
                    tag_row = dict(row)
                else:
                    tag_row = self._create_tag_using_conn(conn, user_id, cleaned)
                key = str(tag_row["tag_id"])
                if key in seen_tag_ids:
                    continue
                seen_tag_ids.add(key)
                resolved.append(tag_row)

        return resolved

    def set_expense_tags(
        self,
        conn: Any,
        user_id: int,
        expense_id: str,
        tag_ids: Optional[List[str]] = None,
        tag_names: Optional[List[str]] = None,
    ) -> List[Dict]:
        resolved = self._resolve_tag_rows(
            conn=conn,
            user_id=user_id,
            tag_ids=tag_ids,
            tag_names=tag_names,
        )
        cur = conn.cursor()
        cur.execute(
            f'DELETE FROM "{SCHEMA}"."{EXPENSE_TAG_TABLE}" WHERE expense_id = %s::uuid',
            (expense_id,),
        )
        now = datetime.now(timezone.utc)
        for row in resolved:
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{EXPENSE_TAG_TABLE}" '
                "(expense_id, tag_id, created_at) "
                "VALUES (%s::uuid, %s::uuid, %s) "
                "ON CONFLICT (expense_id, tag_id) DO NOTHING",
                (expense_id, str(row["tag_id"]), now),
            )
        return resolved

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

    OCR_RESULT_TABLE = "receipt_ocr_result"

    def insert_receipt_ocr_result(self, receipt_id: str, raw_text: Optional[str], extracted_json: Optional[Dict]) -> None:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{self.OCR_RESULT_TABLE}" (receipt_id, raw_text, extracted_json, ocr_run_at) '
                "VALUES (%s::uuid, %s, %s::jsonb, now()) "
                "ON CONFLICT (receipt_id) DO UPDATE SET raw_text = EXCLUDED.raw_text, extracted_json = EXCLUDED.extracted_json, ocr_run_at = now()",
                (receipt_id, raw_text, Json(extracted_json or {})),
            )
        finally:
            conn.close()

    def get_receipt_ocr_result(self, receipt_id: str, user_id: int) -> Optional[Dict]:
        """Return OCR result if receipt exists and belongs to user."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT o.receipt_id, o.raw_text, o.extracted_json, o.ocr_run_at FROM "{SCHEMA}"."{self.OCR_RESULT_TABLE}" o '
                f'JOIN "{SCHEMA}"."{RECEIPT_TABLE}" r ON r.receipt_id = o.receipt_id '
                f'JOIN "{SCHEMA}"."{TABLE}" e ON e.expense_id = r.expense_id AND e.user_id = %s '
                "WHERE o.receipt_id = %s::uuid",
                (user_id, receipt_id),
            )
            row = cur.fetchone()
            return _dict_row(row)
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

    def get_expense_summary_by_currency(
        self,
        user_id: int,
        group_by: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict]:
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
                    SELECT e.category_code::text AS group_key,
                           e.category_name AS label,
                           e.currency AS currency,
                           SUM(e.amount) AS total_amount,
                           COUNT(*) AS count
                    FROM "{SCHEMA}"."{TABLE}" e
                    WHERE {where}
                    GROUP BY e.category_code, e.category_name, e.currency
                    ORDER BY total_amount DESC
                    """,
                    params,
                )
                return [dict(r) for r in cur.fetchall()]
            if group_by == "month":
                cur.execute(
                    f"""
                    SELECT to_char(e.date, 'YYYY-MM') AS group_key,
                           to_char(e.date, 'YYYY-MM') AS label,
                           e.currency AS currency,
                           SUM(e.amount) AS total_amount,
                           COUNT(*) AS count
                    FROM "{SCHEMA}"."{TABLE}" e
                    WHERE {where}
                    GROUP BY to_char(e.date, 'YYYY-MM'), e.currency
                    ORDER BY group_key DESC
                    """,
                    params,
                )
                return [dict(r) for r in cur.fetchall()]
            return []
        finally:
            conn.close()

    def get_expense_totals_by_currency(
        self,
        user_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict]:
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
            cur.execute(
                f"""
                SELECT currency, COALESCE(SUM(amount), 0) AS total_amount, COUNT(*) AS count
                FROM "{SCHEMA}"."{TABLE}"
                WHERE {where}
                GROUP BY currency
                ORDER BY currency ASC
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_latest_exchange_rate(
        self,
        base_currency: str,
        quote_currency: str,
        as_of_date: Optional[date] = None,
        source: Optional[str] = None,
    ) -> Optional[Dict]:
        base = _normalize_currency(base_currency)
        quote = _normalize_currency(quote_currency)
        target_date = as_of_date or datetime.now(timezone.utc).date()
        if base == quote:
            return {
                "base_currency": base,
                "quote_currency": quote,
                "rate": Decimal("1"),
                "rate_date": target_date,
                "source": source or "identity",
            }

        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            if source:
                cur.execute(
                    f"""
                    SELECT base_currency, quote_currency, rate, rate_date, source
                    FROM "{SCHEMA}"."{EXCHANGE_RATE_TABLE}"
                    WHERE base_currency = %s
                      AND quote_currency = %s
                      AND source = %s
                      AND rate_date <= %s
                    ORDER BY rate_date DESC, fetched_at DESC
                    LIMIT 1
                    """,
                    (base, quote, source, target_date),
                )
            else:
                cur.execute(
                    f"""
                    SELECT base_currency, quote_currency, rate, rate_date, source
                    FROM "{SCHEMA}"."{EXCHANGE_RATE_TABLE}"
                    WHERE base_currency = %s
                      AND quote_currency = %s
                      AND rate_date <= %s
                    ORDER BY rate_date DESC, fetched_at DESC
                    LIMIT 1
                    """,
                    (base, quote, target_date),
                )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def convert_amount(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: Optional[date] = None,
    ) -> Optional[Dict]:
        base = _normalize_currency(from_currency)
        quote = _normalize_currency(to_currency)
        rate_row = self.get_latest_exchange_rate(base, quote, as_of_date=as_of_date)
        if not rate_row:
            return None
        rate = Decimal(str(rate_row["rate"]))
        converted_amount = (Decimal(str(amount)) * rate).quantize(Decimal("0.0001"))
        return {
            "from_currency": base,
            "to_currency": quote,
            "rate": rate,
            "rate_date": rate_row["rate_date"],
            "source": rate_row.get("source"),
            "converted_amount": converted_amount,
        }

    def upsert_exchange_rates(
        self,
        rate_date: date,
        source: str,
        rates: List[Dict[str, Any]],
        fetched_at: Optional[datetime] = None,
    ) -> Dict[str, int]:
        upserted_count = 0
        failed_count = 0
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            ts = fetched_at or datetime.now(timezone.utc)
            for item in rates:
                try:
                    base = _normalize_currency(str(item["base_currency"]))
                    quote = _normalize_currency(str(item["quote_currency"]))
                    rate = Decimal(str(item["rate"]))
                    cur.execute(
                        f"""
                        INSERT INTO "{SCHEMA}"."{EXCHANGE_RATE_TABLE}" (
                            base_currency, quote_currency, rate, rate_date, source, fetched_at
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (base_currency, quote_currency, rate_date, source)
                        DO UPDATE SET rate = EXCLUDED.rate, fetched_at = EXCLUDED.fetched_at
                        """,
                        (base, quote, rate, rate_date, source, ts),
                    )
                    upserted_count += 1
                except Exception:
                    failed_count += 1
            return {"upserted_count": upserted_count, "failed_count": failed_count}
        finally:
            conn.close()

    def enrich_expense_export_rows_with_conversion(
        self,
        rows: List[Dict],
        convert_to: str,
        as_of_date: Optional[date] = None,
    ) -> List[Dict]:
        quote = _normalize_currency(convert_to)
        enriched: List[Dict] = []
        for row in rows:
            amount = Decimal(str(row.get("amount") or "0"))
            from_currency = _normalize_currency(row.get("currency") or "USD")
            converted = self.convert_amount(
                amount=amount,
                from_currency=from_currency,
                to_currency=quote,
                as_of_date=as_of_date,
            )
            if not converted:
                raise HTTPException(
                    status_code=422,
                    detail=f"Missing exchange rate for {from_currency}->{quote}",
                )
            item = dict(row)
            item["original_currency"] = from_currency
            item["converted_currency"] = quote
            item["converted_amount"] = converted["converted_amount"]
            item["conversion_rate_date"] = converted["rate_date"]
            item["conversion_source"] = converted.get("source")
            enriched.append(item)
        return enriched

    # --- Income ---
    def create_income(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cols = [
            "user_id", "amount", "date", "currency", "income_type",
            "source_label", "description", "created_at", "updated_at",
        ]
        keys = [k for k in cols if k in data]
        columns = ",".join(f'"{k}"' for k in keys)
        placeholders = ",".join(["%s"] * len(keys))
        vals = [data[k] for k in keys]
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{INCOME_TABLE}" ({columns}) '
                f"VALUES ({placeholders}) RETURNING *",
                vals,
            )
            row = cur.fetchone()
            return _dict_row(row) or data
        finally:
            conn.close()

    def get_income_by_id(self, income_id: str, user_id: int) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{INCOME_TABLE}" '
                "WHERE income_id = %s::uuid AND user_id = %s AND deleted_at IS NULL",
                (income_id, user_id),
            )
            return _dict_row(cur.fetchone())
        finally:
            conn.close()

    def list_income(
        self,
        user_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        income_type: Optional[str] = None,
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
        if income_type:
            conditions.append('income_type = %s')
            params.append(income_type)
        where = " AND ".join(conditions)
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT COUNT(*) AS c FROM "{SCHEMA}"."{INCOME_TABLE}" WHERE {where}',
                params,
            )
            total = cur.fetchone()["c"]
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{INCOME_TABLE}" WHERE {where} '
                "ORDER BY date DESC, created_at DESC, income_id DESC LIMIT %s OFFSET %s",
                params + [limit, offset],
            )
            return [dict(r) for r in cur.fetchall()], total
        finally:
            conn.close()

    def update_income(self, income_id: str, user_id: int, data: Dict[str, Any]) -> Optional[Dict]:
        allowed = {"amount", "date", "currency", "income_type", "source_label", "description", "updated_at"}
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            return self.get_income_by_id(income_id, user_id)
        sets = ", ".join(f'"{k}" = %s' for k in updates)
        params = list(updates.values()) + [income_id, user_id]
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{INCOME_TABLE}" SET {sets} '
                "WHERE income_id = %s::uuid AND user_id = %s AND deleted_at IS NULL",
                params,
            )
            if cur.rowcount == 0:
                return None
            return self.get_income_by_id(income_id, user_id)
        finally:
            conn.close()

    def soft_delete_income(self, income_id: str, user_id: int) -> bool:
        from datetime import datetime, timezone
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{INCOME_TABLE}" '
                "SET deleted_at = %s, updated_at = %s "
                "WHERE income_id = %s::uuid AND user_id = %s AND deleted_at IS NULL",
                (datetime.now(timezone.utc), datetime.now(timezone.utc), income_id, user_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_income_summary(
        self,
        user_id: int,
        group_by: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict]:
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
            if group_by == "type":
                cur.execute(
                    f"""
                    SELECT income_type AS group_key, income_type AS label,
                           SUM(amount) AS total_amount, COUNT(*) AS count
                    FROM "{SCHEMA}"."{INCOME_TABLE}"
                    WHERE {where}
                    GROUP BY income_type
                    ORDER BY total_amount DESC
                    """,
                    params,
                )
                return [dict(r) for r in cur.fetchall()]
            if group_by == "month":
                cur.execute(
                    f"""
                    SELECT to_char(date, 'YYYY-MM') AS group_key,
                           to_char(date, 'YYYY-MM') AS label,
                           SUM(amount) AS total_amount, COUNT(*) AS count
                    FROM "{SCHEMA}"."{INCOME_TABLE}"
                    WHERE {where}
                    GROUP BY to_char(date, 'YYYY-MM')
                    ORDER BY group_key DESC
                    """,
                    params,
                )
                return [dict(r) for r in cur.fetchall()]
            return []
        finally:
            conn.close()

    def get_income_summary_by_currency(
        self,
        user_id: int,
        group_by: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict]:
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
            if group_by == "type":
                cur.execute(
                    f"""
                    SELECT income_type AS group_key,
                           income_type AS label,
                           currency AS currency,
                           SUM(amount) AS total_amount,
                           COUNT(*) AS count
                    FROM "{SCHEMA}"."{INCOME_TABLE}"
                    WHERE {where}
                    GROUP BY income_type, currency
                    ORDER BY total_amount DESC
                    """,
                    params,
                )
                return [dict(r) for r in cur.fetchall()]
            if group_by == "month":
                cur.execute(
                    f"""
                    SELECT to_char(date, 'YYYY-MM') AS group_key,
                           to_char(date, 'YYYY-MM') AS label,
                           currency AS currency,
                           SUM(amount) AS total_amount,
                           COUNT(*) AS count
                    FROM "{SCHEMA}"."{INCOME_TABLE}"
                    WHERE {where}
                    GROUP BY to_char(date, 'YYYY-MM'), currency
                    ORDER BY group_key DESC
                    """,
                    params,
                )
                return [dict(r) for r in cur.fetchall()]
            return []
        finally:
            conn.close()

    def get_income_total(
        self,
        user_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Decimal:
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
            cur.execute(
                f'SELECT COALESCE(SUM(amount), 0) AS total FROM "{SCHEMA}"."{INCOME_TABLE}" WHERE {where}',
                params,
            )
            row = cur.fetchone()
            return row["total"] if row and row.get("total") is not None else Decimal("0")
        finally:
            conn.close()

    def get_income_totals_by_currency(
        self,
        user_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict]:
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
            cur.execute(
                f"""
                SELECT currency, COALESCE(SUM(amount), 0) AS total_amount, COUNT(*) AS count
                FROM "{SCHEMA}"."{INCOME_TABLE}"
                WHERE {where}
                GROUP BY currency
                ORDER BY currency ASC
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_expense_total(
        self,
        user_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Decimal:
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
            cur.execute(
                f'SELECT COALESCE(SUM(amount), 0) AS total FROM "{SCHEMA}"."{TABLE}" WHERE {where}',
                params,
            )
            row = cur.fetchone()
            return row["total"] if row and row.get("total") is not None else Decimal("0")
        finally:
            conn.close()

    # --- Recurring expenses ---
    def create_recurring_expense(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cols = [
            "user_id", "amount", "currency", "category_code", "category_name",
            "description", "recurrence_rule", "next_due_date", "is_active",
            "created_at", "updated_at",
        ]
        keys = [k for k in cols if k in data]
        columns = ",".join(f'"{k}"' for k in keys)
        placeholders = ",".join(["%s"] * len(keys))
        vals = [data[k] for k in keys]
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{RECURRING_TABLE}" ({columns}) '
                f"VALUES ({placeholders}) RETURNING *",
                vals,
            )
            row = cur.fetchone()
            return _dict_row(row) or data
        finally:
            conn.close()

    def get_recurring_expense_by_id(self, recurring_id: str, user_id: int) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{RECURRING_TABLE}" '
                "WHERE recurring_id = %s::uuid AND user_id = %s",
                (recurring_id, user_id),
            )
            return _dict_row(cur.fetchone())
        finally:
            conn.close()

    def list_recurring_expenses(
        self,
        user_id: int,
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict], int]:
        conditions = ["user_id = %s"]
        params: List[Any] = [user_id]
        if active_only:
            conditions.append("is_active = true")
        where = " AND ".join(conditions)
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT COUNT(*) AS c FROM "{SCHEMA}"."{RECURRING_TABLE}" WHERE {where}',
                params,
            )
            total = cur.fetchone()["c"]
            cur.execute(
                f'SELECT * FROM "{SCHEMA}"."{RECURRING_TABLE}" WHERE {where} '
                "ORDER BY next_due_date ASC, created_at DESC LIMIT %s OFFSET %s",
                params + [limit, offset],
            )
            return [dict(r) for r in cur.fetchall()], total
        finally:
            conn.close()

    def update_recurring_expense(self, recurring_id: str, user_id: int, data: Dict[str, Any]) -> Optional[Dict]:
        allowed = {
            "amount", "currency", "category_code", "category_name", "description",
            "recurrence_rule", "next_due_date", "is_active", "last_run_at",
            "last_created_expense_id", "updated_at",
        }
        updates = {k: v for k, v in data.items() if k in allowed and v is not None}
        if not updates:
            return self.get_recurring_expense_by_id(recurring_id, user_id)
        sets = ", ".join(f'"{k}" = %s' for k in updates)
        params = list(updates.values()) + [recurring_id, user_id]
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{RECURRING_TABLE}" SET {sets} '
                "WHERE recurring_id = %s::uuid AND user_id = %s",
                params,
            )
            if cur.rowcount == 0:
                return None
            return self.get_recurring_expense_by_id(recurring_id, user_id)
        finally:
            conn.close()

    def delete_recurring_expense(self, recurring_id: str, user_id: int) -> bool:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{RECURRING_TABLE}" '
                "WHERE recurring_id = %s::uuid AND user_id = %s",
                (recurring_id, user_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def list_expenses_for_export(
        self,
        user_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict]:
        conditions = ['user_id = %s', 'deleted_at IS NULL']
        params: List[Any] = [user_id]
        if date_from:
            conditions.append('date >= %s')
            params.append(date_from)
        if date_to:
            conditions.append('date <= %s')
            params.append(date_to)
        where = " AND ".join(conditions)
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT expense_id, user_id, amount, date, currency, category_code, category_name, '
                "description, source, plaid_transaction_id, created_at, updated_at "
                f'FROM "{SCHEMA}"."{TABLE}" WHERE {where} ORDER BY date DESC, created_at DESC',
                params,
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def list_due_recurring_ids(self, as_of_date: date, limit: int = 500) -> List[str]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT recurring_id::text
                FROM "{SCHEMA}"."{RECURRING_TABLE}"
                WHERE is_active = true
                  AND next_due_date <= %s
                ORDER BY next_due_date ASC, created_at ASC, recurring_id ASC
                LIMIT %s
                """,
                (as_of_date, max(1, limit)),
            )
            rows = cur.fetchall()
            return [str(r["recurring_id"]) for r in rows]
        finally:
            conn.close()

    def process_single_due_recurring(self, recurring_id: str, as_of_date: date) -> bool:
        """
        Process one recurring template atomically.
        Returns True if an expense was created and recurring metadata advanced, else False.
        """
        conn = self.get_connection(autocommit=False)
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT recurring_id::text, user_id, amount, currency, category_code, category_name,
                       description, recurrence_rule, next_due_date, is_active
                FROM "{SCHEMA}"."{RECURRING_TABLE}"
                WHERE recurring_id = %s::uuid
                FOR UPDATE
                """,
                (recurring_id,),
            )
            recurring = cur.fetchone()
            if not recurring:
                conn.commit()
                return False

            if not recurring.get("is_active", True):
                conn.commit()
                return False

            due_date = recurring.get("next_due_date")
            if not isinstance(due_date, date):
                conn.commit()
                return False

            if due_date > as_of_date:
                conn.commit()
                return False

            user_id = int(recurring["user_id"])
            self.acquire_user_lock(conn, user_id)

            now = datetime.now(timezone.utc)
            expense_data: Dict[str, Any] = {
                "user_id": user_id,
                "category_code": int(recurring["category_code"]),
                "category_name": recurring["category_name"],
                "amount": Decimal(str(recurring["amount"])),
                "date": due_date,
                "currency": str(recurring.get("currency") or "USD").upper(),
                "description": recurring.get("description"),
                "balance_after": None,
                "created_at": now,
                "updated_at": now,
                "source": "recurring",
            }
            self._insert_expense_using_conn(conn, expense_data)

            expense_id = expense_data["expense_id"]
            prev = self.get_previous_expense(
                user_id=user_id,
                date_val=due_date.isoformat(),
                created_at=expense_data["created_at"],
                expense_id=expense_id,
                conn=conn,
            )
            balance_before = Decimal("0")
            if prev and prev.get("balance_after") is not None:
                balance_before = Decimal(str(prev["balance_after"]))
            new_balance = balance_before + Decimal(str(expense_data["amount"]))
            self.update_expense_balance_after(conn, str(expense_id), user_id, new_balance)
            self.recalc_balance_after(
                conn,
                user_id,
                due_date.isoformat(),
                expense_data["created_at"],
                str(expense_id),
                new_balance,
            )

            next_due_date = _advance_due_date(due_date, str(recurring["recurrence_rule"]))
            cur.execute(
                f"""
                UPDATE "{SCHEMA}"."{RECURRING_TABLE}"
                SET next_due_date = %s,
                    last_run_at = %s,
                    last_created_expense_id = %s::uuid,
                    updated_at = %s
                WHERE recurring_id = %s::uuid
                  AND is_active = true
                  AND next_due_date = %s
                """,
                (
                    next_due_date,
                    now,
                    str(expense_id),
                    now,
                    recurring_id,
                    due_date,
                ),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return False

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def process_due_recurring_batch(
        self,
        as_of_date: date,
        limit: int = 500,
    ) -> Dict[str, Any]:
        recurring_ids = self.list_due_recurring_ids(as_of_date=as_of_date, limit=limit)
        processed_count = 0
        skipped_count = 0
        failed_count = 0
        failures: List[Dict[str, str]] = []

        for recurring_id in recurring_ids:
            try:
                processed = self.process_single_due_recurring(recurring_id, as_of_date)
                if processed:
                    processed_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                failed_count += 1
                failures.append(
                    {
                        "recurring_id": recurring_id,
                        "error": str(e),
                    }
                )

        return {
            "as_of_date": as_of_date.isoformat(),
            "candidate_count": len(recurring_ids),
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "failures": failures,
        }

    def get_idempotent_expense_id(self, user_id: int, idempotency_key: str) -> Optional[str]:
        """Return expense_id if key was used within TTL, else None."""
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

    def purge_user_data(self, user_id: int) -> Dict[str, int]:
        conn = self.get_connection(autocommit=False)
        try:
            cur = conn.cursor()
            summary: Dict[str, int] = {}

            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{self.RECEIPT_TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            summary["receipts_deleted"] = cur.rowcount or 0

            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{IDEMPOTENCY_TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            summary["idempotency_deleted"] = cur.rowcount or 0

            cur.execute(
                f'DELETE FROM "{SCHEMA}".plaid_item WHERE user_id = %s',
                (user_id,),
            )
            summary["plaid_items_deleted"] = cur.rowcount or 0

            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{RECURRING_TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            summary["recurring_deleted"] = cur.rowcount or 0

            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{INCOME_TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            summary["income_deleted"] = cur.rowcount or 0

            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            summary["expenses_deleted"] = cur.rowcount or 0

            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TAG_TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            summary["tags_deleted"] = cur.rowcount or 0

            conn.commit()
            return summary
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- Expense import (Phase 3) ---
    IMPORT_JOB_TABLE = "expense_import_job"
    IMPORT_ROW_TABLE = "expense_import_row"

    def create_import_job(self, user_id: int, household_id: Optional[str], filename: str) -> Dict[str, Any]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{self.IMPORT_JOB_TABLE}" (user_id, household_id, filename, status) '
                "VALUES (%s, %s, %s, 'uploaded') RETURNING job_id, user_id, household_id, filename, status, created_at, updated_at",
                (user_id, household_id, filename),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def add_import_row(self, job_id: str, row_number: int, raw_payload: Optional[Dict], normalized_payload: Optional[Dict], validation_error: Optional[str], is_duplicate: bool) -> None:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'INSERT INTO "{SCHEMA}"."{self.IMPORT_ROW_TABLE}" (job_id, row_number, raw_payload, normalized_payload, validation_error, is_duplicate) '
                "VALUES (%s::uuid, %s, %s, %s, %s, %s)",
                (job_id, row_number, Json(raw_payload) if raw_payload else None, Json(normalized_payload) if normalized_payload else None, validation_error, is_duplicate),
            )
        finally:
            conn.close()

    def get_import_job(self, job_id: str, user_id: int) -> Optional[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT job_id, user_id, household_id, filename, status, created_at, updated_at FROM "{SCHEMA}"."{self.IMPORT_JOB_TABLE}" WHERE job_id = %s AND user_id = %s',
                (job_id, user_id),
            )
            row = cur.fetchone()
            return _dict_row(row)
        finally:
            conn.close()

    def get_import_rows(self, job_id: str) -> List[Dict]:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT job_id, row_number, raw_payload, normalized_payload, validation_error, is_duplicate, created_at '
                f'FROM "{SCHEMA}"."{self.IMPORT_ROW_TABLE}" WHERE job_id = %s ORDER BY row_number',
                (job_id,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def update_import_job_status(self, job_id: str, user_id: int, status: str) -> None:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'UPDATE "{SCHEMA}"."{self.IMPORT_JOB_TABLE}" SET status = %s, updated_at = now() WHERE job_id = %s AND user_id = %s',
                (status, job_id, user_id),
            )
        finally:
            conn.close()

    def expense_exists_duplicate(self, user_id: int, household_id: Optional[str], date_str: str, amount: Decimal, description_norm: Optional[str]) -> bool:
        """Check if an expense with same user, household, date, amount (and optional description) already exists."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            conditions = ["user_id = %s", "date = %s", "amount = %s", "deleted_at IS NULL"]
            params: List[Any] = [user_id, date_str, amount]
            if household_id is None:
                conditions.append("household_id IS NULL")
            else:
                conditions.append("household_id = %s::uuid")
                params.append(household_id)
            if description_norm:
                conditions.append("TRIM(LOWER(COALESCE(description, ''))) = %s")
                params.append(description_norm[:500] if len(description_norm) > 500 else description_norm)
            cur.execute(
                f'SELECT 1 FROM "{SCHEMA}"."{TABLE}" WHERE ' + " AND ".join(conditions) + " LIMIT 1",
                params,
            )
            return cur.fetchone() is not None
        finally:
            conn.close()

    def commit_import_job(self, job_id: str, user_id: int) -> Dict[str, int]:
        """Insert valid non-duplicate rows as expenses. Returns counts. Idempotent: if already committed, return stored counts or recompute."""
        job = self.get_import_job(job_id, user_id)
        if not job:
            raise HTTPException(status_code=404, detail="Import job not found")
        if job.get("status") == "committed":
            rows = self.get_import_rows(job_id)
            valid = sum(1 for r in rows if not r.get("validation_error") and not r.get("is_duplicate"))
            inserted = sum(1 for r in rows if r.get("normalized_payload") and not r.get("validation_error") and not r.get("is_duplicate"))
            return {"total_rows": len(rows), "valid_rows": valid, "invalid_rows": sum(1 for r in rows if r.get("validation_error")), "duplicate_rows": sum(1 for r in rows if r.get("is_duplicate")), "inserted_rows": inserted}
        rows = self.get_import_rows(job_id)
        inserted = 0
        household_id = str(job["household_id"]) if job.get("household_id") else None
        data_for_household = {}
        if household_id:
            data_for_household["household_id"] = household_id
        conn = self.get_connection(autocommit=False)
        try:
            for r in rows:
                if r.get("validation_error") or r.get("is_duplicate"):
                    continue
                np = r.get("normalized_payload") or {}
                date_val = np.get("date")
                amount_val = np.get("amount")
                if not date_val or amount_val is None:
                    continue
                cat_code = np.get("category_code") or 8
                cat_name = np.get("category_name") or "Other"
                currency = (np.get("currency") or "USD")[:3]
                desc = (np.get("description") or "")[:2000]
                data = {
                    "user_id": user_id,
                    "category_code": cat_code,
                    "category_name": cat_name,
                    "amount": amount_val,
                    "date": date_val,
                    "currency": currency,
                    "description": desc or None,
                    "balance_after": None,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    **data_for_household,
                }
                self._insert_expense_using_conn(conn, data)
                expense_id = data.get("expense_id")
                created_at = data.get("created_at")
                if expense_id and created_at:
                    self.recalc_balance_after(conn, user_id, date_val, created_at, str(expense_id), None)
                inserted += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        self.update_import_job_status(job_id, user_id, "committed")
        invalid = sum(1 for r in rows if r.get("validation_error"))
        dup = sum(1 for r in rows if r.get("is_duplicate"))
        valid = len(rows) - invalid
        return {"total_rows": len(rows), "valid_rows": valid, "invalid_rows": invalid, "duplicate_rows": dup, "inserted_rows": inserted}
