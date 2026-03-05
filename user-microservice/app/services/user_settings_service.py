"""
Per-user settings service (Phase 2 currency preferences).
"""
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

SCHEMA = "users_db"
TABLE = "user_settings"


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def get_user_settings(user_id: int) -> dict[str, Any]:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'SELECT user_id, default_currency, updated_at '
            f'FROM "{SCHEMA}"."{TABLE}" '
            "WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        now = datetime.now(timezone.utc)
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{TABLE}" (user_id, default_currency, updated_at) '
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET updated_at = EXCLUDED.updated_at "
            "RETURNING user_id, default_currency, updated_at",
            (user_id, "USD", now),
        )
        created = cur.fetchone()
        return dict(created) if created else {"user_id": user_id, "default_currency": "USD", "updated_at": now}
    finally:
        conn.close()


def update_default_currency(user_id: int, default_currency: str) -> dict[str, Any]:
    currency = str(default_currency or "").strip().upper()
    if len(currency) != 3:
        raise ValueError("default_currency must be a 3-letter code")
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        cur.execute(
            f"""
            INSERT INTO "{SCHEMA}"."{TABLE}" (user_id, default_currency, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET default_currency = EXCLUDED.default_currency, updated_at = EXCLUDED.updated_at
            RETURNING user_id, default_currency, updated_at
            """,
            (user_id, currency, now),
        )
        row = cur.fetchone()
        return dict(row) if row else {"user_id": user_id, "default_currency": currency, "updated_at": now}
    finally:
        conn.close()
