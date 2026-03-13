"""Phase 4: Saved report views (filter payload per user)."""
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

SCHEMA = "users_db"
TABLE = "report_saved_view"


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def create_saved_view(user_id: int, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    import json
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{TABLE}" (user_id, name, payload_json) '
            "VALUES (%s, %s, %s::jsonb) RETURNING view_id, user_id, name, payload_json, created_at, updated_at",
            (user_id, name[:255], json.dumps(payload or {})),
        )
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def list_saved_views(user_id: int) -> List[Dict[str, Any]]:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'SELECT view_id, user_id, name, payload_json, created_at, updated_at FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s ORDER BY updated_at DESC',
            (user_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_saved_view(view_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'SELECT view_id, user_id, name, payload_json, created_at, updated_at FROM "{SCHEMA}"."{TABLE}" WHERE view_id = %s::uuid AND user_id = %s',
            (view_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_saved_view(view_id: str, user_id: int) -> bool:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE view_id = %s::uuid AND user_id = %s',
            (view_id, user_id),
        )
        return cur.rowcount > 0
    finally:
        conn.close()
