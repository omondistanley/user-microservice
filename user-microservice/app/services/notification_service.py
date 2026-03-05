"""
User notification inbox service.
"""
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

SCHEMA = "users_db"
TABLE = "user_notification"


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def create_notification(
    user_id: int,
    notification_type: str,
    title: str,
    body: str,
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{TABLE}" '
            "(user_id, type, title, body, is_read, payload_json, created_at) "
            "VALUES (%s, %s, %s, %s, false, %s, %s) "
            "RETURNING notification_id, user_id, type, title, body, is_read, payload_json, created_at, read_at",
            (
                user_id,
                notification_type,
                title,
                body,
                Json(payload) if payload is not None else None,
                now,
            ),
        )
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def list_notifications(user_id: int, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int, int]:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'SELECT COUNT(*) AS c FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s',
            (user_id,),
        )
        total = int(cur.fetchone()["c"])
        cur.execute(
            f'SELECT COUNT(*) AS c FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s AND is_read = false',
            (user_id,),
        )
        unread = int(cur.fetchone()["c"])
        cur.execute(
            f'SELECT notification_id, user_id, type, title, body, is_read, payload_json, created_at, read_at '
            f'FROM "{SCHEMA}"."{TABLE}" '
            "WHERE user_id = %s "
            "ORDER BY created_at DESC "
            "LIMIT %s OFFSET %s",
            (user_id, max(1, limit), max(0, offset)),
        )
        items = [dict(r) for r in cur.fetchall()]
        return items, total, unread
    finally:
        conn.close()


def mark_notification_read(user_id: int, notification_id: str) -> Optional[dict[str, Any]]:
    conn = _get_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            f'SELECT notification_id, user_id, type, title, body, is_read, payload_json, created_at, read_at '
            f'FROM "{SCHEMA}"."{TABLE}" '
            "WHERE user_id = %s AND notification_id = %s::uuid",
            (user_id, notification_id),
        )
        existing = cur.fetchone()
        if not existing:
            conn.rollback()
            return None

        if not existing.get("is_read"):
            now = datetime.now(timezone.utc)
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" '
                "SET is_read = true, read_at = COALESCE(read_at, %s) "
                "WHERE user_id = %s AND notification_id = %s::uuid",
                (now, user_id, notification_id),
            )
        conn.commit()
        cur.execute(
            f'SELECT notification_id, user_id, type, title, body, is_read, payload_json, created_at, read_at '
            f'FROM "{SCHEMA}"."{TABLE}" '
            "WHERE user_id = %s AND notification_id = %s::uuid",
            (user_id, notification_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_all_notifications_read(user_id: int) -> int:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'UPDATE "{SCHEMA}"."{TABLE}" '
            "SET is_read = true, read_at = COALESCE(read_at, %s) "
            "WHERE user_id = %s AND is_read = false",
            (datetime.now(timezone.utc), user_id),
        )
        return cur.rowcount or 0
    finally:
        conn.close()
