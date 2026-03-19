"""SQLite for interactive demo only.

Backs the `demo-app` sandbox (watch + interactive).
All demo analytics must be derived from sandbox rows only.
"""
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Generator, List, Optional

from app.config import DEMO_DB_PATH

_lock = threading.Lock()

# Watch demo seed (read-only). This data is deterministic and must not depend on time.
WATCH_SESSION_ID = "watch"
WATCH_DEFAULT_MONTH = "2026-03"

# Keys used by watch routes to show “detail” screens without relying on unstable autoincrement IDs.
WATCH_EXPENSES_BY_KEY = {
    "coffee": {
        "expense_date": "2026-03-14",
        "description": "Coffee",
        "category": "Food",
        "amount": 6.50,
    },
    "transit_pass": {
        "expense_date": "2026-03-15",
        "description": "Transit pass",
        "category": "Transit",
        "amount": 35.00,
    },
    "grocery_co": {
        "expense_date": "2026-03-16",
        "description": "Grocery Co",
        "category": "Food",
        "amount": 48.20,
    },
    "food_big": {
        "expense_date": "2026-03-10",
        "description": "Food big",
        "category": "Food",
        "amount": 210.00,
    },
    "entertainment": {
        "expense_date": "2026-03-12",
        "description": "Cinema",
        "category": "Entertainment",
        "amount": 42.75,
    },
    # prior months (for forecast/anomaly context)
    "coffee_prev_1": {
        "expense_date": "2026-02-14",
        "description": "Coffee",
        "category": "Food",
        "amount": 5.90,
    },
    "coffee_prev_2": {
        "expense_date": "2026-01-14",
        "description": "Coffee",
        "category": "Food",
        "amount": 5.50,
    },
    "transit_prev": {
        "expense_date": "2026-02-15",
        "description": "Transit pass",
        "category": "Transit",
        "amount": 33.00,
    },
}

WATCH_BUDGETS_BY_KEY = {
    "food_2026_03": {"month": "2026-03", "category": "Food", "limit": 500.00},
    "transit_2026_03": {"month": "2026-03", "category": "Transit", "limit": 150.00},
    "ent_2026_03": {"month": "2026-03", "category": "Entertainment", "limit": 120.00},
    "food_2026_02": {"month": "2026-02", "category": "Food", "limit": 480.00},
    "transit_2026_02": {"month": "2026-02", "category": "Transit", "limit": 160.00},
    "ent_2026_02": {"month": "2026-02", "category": "Entertainment", "limit": 100.00},
}


def ensure_watch_seed() -> None:
    """Ensure deterministic watch demo data exists in SQLite.

    Reset jobs wipe demo tables, so we re-seed watch rows after each reset.
    """
    # Seed inserts are deterministic; IDs are not relied upon by watch routes.
    with get_conn() as conn:
        conn.execute("DELETE FROM demo_expense WHERE session_id=?", (WATCH_SESSION_ID,))
        conn.execute("DELETE FROM demo_budget WHERE session_id=?", (WATCH_SESSION_ID,))
        conn.execute(
            "DELETE FROM demo_insights_feedback WHERE session_id=?", (WATCH_SESSION_ID,)
        )

        expenses_rows = []
        for _, e in WATCH_EXPENSES_BY_KEY.items():
            expenses_rows.append(
                (
                    WATCH_SESSION_ID,
                    float(e["amount"]),
                    str(e["description"]),
                    _normalize_category(e["category"]),
                    str(e["expense_date"])[:10],
                )
            )
        conn.executemany(
            """
            INSERT INTO demo_expense(session_id, amount, description, category, expense_date)
            VALUES (?,?,?,?,?)
            """,
            expenses_rows,
        )

        budgets_rows = []
        for _, b in WATCH_BUDGETS_BY_KEY.items():
            budgets_rows.append(
                (
                    WATCH_SESSION_ID,
                    str(b["month"])[:7],
                    _normalize_category(b["category"]),
                    float(b["limit"]),
                )
            )
        conn.executemany(
            """
            INSERT INTO demo_budget(session_id, month, category, limit_amount)
            VALUES (?,?,?,?)
            """,
            budgets_rows,
        )


def _ensure_parent(path: str) -> None:
    import os
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def init_db() -> None:
    _ensure_parent(DEMO_DB_PATH)
    with _lock:
        conn = sqlite3.connect(DEMO_DB_PATH)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS demo_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS demo_expense (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT,
                    expense_date TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS demo_budget (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    month TEXT NOT NULL,          -- YYYY-MM
                    category TEXT NOT NULL,
                    limit_amount REAL NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(session_id, month, category)
                );
                CREATE TABLE IF NOT EXISTS demo_insights_feedback (
                    session_id TEXT NOT NULL,
                    expense_id INTEGER NOT NULL,
                    decision TEXT NOT NULL, -- 'valid' | 'ignore'
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(session_id, expense_id)
                );
                CREATE TABLE IF NOT EXISTS demo_ai_cache (
                    scene_id TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS demo_ai_usage (
                    day TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS demo_income (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    source TEXT NOT NULL,
                    income_date TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS demo_goal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    target_amount REAL NOT NULL,
                    current_amount REAL NOT NULL DEFAULT 0,
                    deadline TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    _ensure_parent(DEMO_DB_PATH)
    conn = sqlite3.connect(DEMO_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def reset_demo_data() -> None:
    """Wipe user-created sandbox rows (keeps schema)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM demo_expense")
        conn.execute("DELETE FROM demo_budget")
        conn.execute("DELETE FROM demo_insights_feedback")
        conn.execute("DELETE FROM demo_income")
        conn.execute("DELETE FROM demo_goal")
        conn.execute(
            "INSERT OR REPLACE INTO demo_meta(key,value) VALUES ('last_reset', datetime('now'))"
        )


def last_activity_iso() -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM demo_meta WHERE key='last_activity'"
        ).fetchone()
        return row["value"] if row else None


def last_reset_iso() -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM demo_meta WHERE key='last_reset'"
        ).fetchone()
        return row["value"] if row else None


def touch_activity() -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO demo_meta(key,value) VALUES ('last_activity', datetime('now'))"
        )


def _expense_month(expense_date: str) -> Optional[str]:
    """Derive `YYYY-MM` month from `YYYY-MM-DD` expense_date."""
    if not expense_date or len(expense_date) < 7:
        return None
    return expense_date[:7]


def _normalize_category(category: str) -> str:
    c = (category or "").strip()
    return c[:64] if c else "Other"


def list_expenses(session_id: str) -> List[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """SELECT id, amount, description, category, expense_date
               FROM demo_expense WHERE session_id=? ORDER BY id DESC""",
            (session_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def count_expenses(session_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(COUNT(*),0) AS cnt FROM demo_expense WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return int(row["cnt"] if row else 0)


def count_budgets(session_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(COUNT(*),0) AS cnt FROM demo_budget WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return int(row["cnt"] if row else 0)


def add_expense(
    session_id: str, amount: float, description: str, category: str, expense_date: str
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO demo_expense(session_id, amount, description, category, expense_date)
               VALUES (?,?,?,?,?)""",
            (session_id, amount, description, _normalize_category(category), expense_date),
        )
        return int(cur.lastrowid or 0)


def get_expense(session_id: str, expense_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, amount, description, category, expense_date
            FROM demo_expense
            WHERE id=? AND session_id=?
            """,
            (expense_id, session_id),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["category"] = _normalize_category(d.get("category", "Other"))
        return d


def update_expense(
    session_id: str,
    expense_id: int,
    amount: float,
    description: str,
    category: str,
    expense_date: str,
) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE demo_expense
            SET amount=?, description=?, category=?, expense_date=?
            WHERE id=? AND session_id=?
            """,
            (
                amount,
                description,
                _normalize_category(category),
                expense_date,
                expense_id,
                session_id,
            ),
        )
        return bool(cur.rowcount)


def list_budgets(session_id: str, month: Optional[str] = None) -> List[dict]:
    with get_conn() as conn:
        if month:
            cur = conn.execute(
                """SELECT id, month, category, limit_amount AS "limit"
                   FROM demo_budget
                   WHERE session_id=? AND month=?
                   ORDER BY category ASC""",
                (session_id, month),
            )
        else:
            cur = conn.execute(
                """SELECT id, month, category, limit_amount AS "limit"
                   FROM demo_budget
                   WHERE session_id=?
                   ORDER BY month DESC, category ASC""",
                (session_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def add_budget(session_id: str, month: str, category: str, limit: float) -> int:
    """Create-or-update a session-scoped budget for (month, category)."""
    category_n = _normalize_category(category)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO demo_budget(session_id, month, category, limit_amount)
            VALUES (?,?,?,?)
            ON CONFLICT(session_id, month, category) DO UPDATE SET
              limit_amount=excluded.limit_amount,
              updated_at=datetime('now')
            """,
            (session_id, month, category_n, limit),
        )
        row = conn.execute(
            """SELECT id FROM demo_budget WHERE session_id=? AND month=? AND category=?""",
            (session_id, month, category_n),
        ).fetchone()
        return int(row["id"] if row else 0)


def update_budget(
    session_id: str, budget_id: int, month: str, category: str, limit: float
) -> bool:
    category_n = _normalize_category(category)
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE demo_budget
            SET month=?, category=?, limit_amount=?, updated_at=datetime('now')
            WHERE id=? AND session_id=?
            """,
            (month, category_n, limit, budget_id, session_id),
        )
        return bool(cur.rowcount)


def get_budget(session_id: str, budget_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, session_id, month, category, limit_amount AS "limit"
            FROM demo_budget
            WHERE id=? AND session_id=?
            """,
            (budget_id, session_id),
        ).fetchone()
        return dict(row) if row else None


def expense_month_totals(session_id: str) -> List[dict]:
    """Monthly totals derived from sandbox expenses (month = YYYY-MM)."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT substr(expense_date, 1, 7) AS month,
                   SUM(amount) AS total
            FROM demo_expense
            WHERE session_id=?
            GROUP BY substr(expense_date, 1, 7)
            ORDER BY month DESC
            """,
            (session_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def category_spend_for_month(session_id: str, month: str) -> List[dict]:
    """Category totals for a specific `month` (YYYY-MM)."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT COALESCE(category,'Other') AS category,
                   SUM(amount) AS total
            FROM demo_expense
            WHERE session_id=?
              AND substr(expense_date, 1, 7)=?
            GROUP BY COALESCE(category,'Other')
            ORDER BY total DESC
            """,
            (session_id, month),
        )
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["category"] = _normalize_category(r.get("category", "Other"))
        return rows


def total_spend_for_month(session_id: str, month: str) -> float:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS total
            FROM demo_expense
            WHERE session_id=?
              AND substr(expense_date, 1, 7)=?
            """,
            (session_id, month),
        ).fetchone()
        return float(row["total"] if row else 0.0)


def spend_for_category_month(session_id: str, category: str, month: str) -> float:
    category_n = _normalize_category(category)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS total
            FROM demo_expense
            WHERE session_id=?
              AND category=?
              AND substr(expense_date, 1, 7)=?
            """,
            (session_id, category_n, month),
        ).fetchone()
        return float(row["total"] if row else 0.0)


def list_expenses_for_month(session_id: str, month: str) -> List[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, amount, description, category, expense_date
            FROM demo_expense
            WHERE session_id=?
              AND substr(expense_date, 1, 7)=?
            ORDER BY expense_date DESC, id DESC
            """,
            (session_id, month),
        )
        return [dict(r) for r in cur.fetchall()]


def set_insights_feedback(
    session_id: str, expense_id: int, decision: str
) -> None:
    decision_n = (decision or "").strip().lower()
    if decision_n not in ("valid", "ignore"):
        decision_n = "ignore"
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO demo_insights_feedback(session_id, expense_id, decision)
            VALUES (?,?,?)
            ON CONFLICT(session_id, expense_id) DO UPDATE SET
              decision=excluded.decision,
              created_at=datetime('now')
            """,
            (session_id, expense_id, decision_n),
        )


# --- Income (session-scoped) ---
def list_income(session_id: str) -> List[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """SELECT id, amount, source, income_date
               FROM demo_income WHERE session_id=? ORDER BY income_date DESC, id DESC""",
            (session_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def add_income(
    session_id: str, amount: float, source: str, income_date: str
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO demo_income(session_id, amount, source, income_date)
               VALUES (?,?,?,?)""",
            (session_id, amount, (source or "Other")[:64], income_date[:10]),
        )
        return int(cur.lastrowid or 0)


def get_income(session_id: str, income_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, amount, source, income_date
               FROM demo_income WHERE id=? AND session_id=?""",
            (income_id, session_id),
        ).fetchone()
        return dict(row) if row else None


def update_income(
    session_id: str, income_id: int, amount: float, source: str, income_date: str
) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE demo_income
               SET amount=?, source=?, income_date=?
               WHERE id=? AND session_id=?""",
            (amount, (source or "Other")[:64], income_date[:10], income_id, session_id),
        )
        return bool(cur.rowcount)


def count_income(session_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(COUNT(*),0) AS cnt FROM demo_income WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return int(row["cnt"] if row else 0)


# --- Goals (session-scoped) ---
def list_goals(session_id: str) -> List[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """SELECT id, name, target_amount, current_amount, deadline
               FROM demo_goal WHERE session_id=? ORDER BY id DESC""",
            (session_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def add_goal(
    session_id: str,
    name: str,
    target_amount: float,
    current_amount: float = 0.0,
    deadline: Optional[str] = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO demo_goal(session_id, name, target_amount, current_amount, deadline)
               VALUES (?,?,?,?,?)""",
            (
                session_id,
                (name or "Goal")[:256],
                target_amount,
                current_amount,
                deadline[:10] if deadline else None,
            ),
        )
        return int(cur.lastrowid or 0)


def get_goal(session_id: str, goal_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, name, target_amount, current_amount, deadline
               FROM demo_goal WHERE id=? AND session_id=?""",
            (goal_id, session_id),
        ).fetchone()
        return dict(row) if row else None


def update_goal(
    session_id: str,
    goal_id: int,
    *,
    name: Optional[str] = None,
    target_amount: Optional[float] = None,
    current_amount: Optional[float] = None,
    deadline: Optional[str] = None,
) -> bool:
    with get_conn() as conn:
        updates = []
        params: List[Any] = []
        if name is not None:
            updates.append("name=?")
            params.append((name or "Goal")[:256])
        if target_amount is not None:
            updates.append("target_amount=?")
            params.append(target_amount)
        if current_amount is not None:
            updates.append("current_amount=?")
            params.append(current_amount)
        if deadline is not None:
            updates.append("deadline=?")
            params.append(deadline[:10] if deadline else None)
        if not updates:
            return True
        updates.append("updated_at=datetime('now')")
        params.extend([goal_id, session_id])
        cur = conn.execute(
            f"UPDATE demo_goal SET {', '.join(updates)} WHERE id=? AND session_id=?",
            params,
        )
        return bool(cur.rowcount)


def count_goals(session_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(COUNT(*),0) AS cnt FROM demo_goal WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return int(row["cnt"] if row else 0)


def get_ai_cache(scene_id: str) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT body FROM demo_ai_cache WHERE scene_id=?", (scene_id,)
        ).fetchone()
        return row["body"] if row else None


def set_ai_cache(scene_id: str, body: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO demo_ai_cache(scene_id, body) VALUES (?,?)",
            (scene_id, body),
        )


def ai_usage_today() -> int:
    from datetime import date

    day = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count FROM demo_ai_usage WHERE day=?", (day,)
        ).fetchone()
        return int(row["count"]) if row else 0


def increment_ai_usage() -> None:
    from datetime import date

    day = date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO demo_ai_usage(day, count) VALUES (?,1)
               ON CONFLICT(day) DO UPDATE SET count = count + 1""",
            (day,),
        )
