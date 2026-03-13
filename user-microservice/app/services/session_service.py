"""
Phase 5: User session tracking (no 2FA). Create/list/revoke sessions.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

SCHEMA = "users_db"
TABLE = "user_session"
REFRESH_TABLE = "refresh_token"


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def create_session(user_id: int, device_meta: Optional[str] = None) -> str:
    """Create a new session. Returns session_id (uuid string)."""
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        meta = (device_meta or "")[:512]
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{TABLE}" (user_id, device_meta, issued_at, last_seen_at) '
            "VALUES (%s, %s, now(), now()) RETURNING session_id",
            (user_id, meta or None),
        )
        row = cur.fetchone()
        return str(row["session_id"]) if row else ""
    finally:
        conn.close()


def update_last_seen(session_id: str) -> None:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'UPDATE "{SCHEMA}"."{TABLE}" SET last_seen_at = now() WHERE session_id = %s::uuid',
            (session_id,),
        )
    finally:
        conn.close()


def list_sessions(user_id: int, include_revoked: bool = False) -> List[Dict[str, Any]]:
    """List sessions for user. By default only active (revoked_at IS NULL)."""
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        if include_revoked:
            cur.execute(
                f'SELECT session_id, user_id, device_meta, issued_at, last_seen_at, revoked_at '
                f'FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s ORDER BY last_seen_at DESC',
                (user_id,),
            )
        else:
            cur.execute(
                f'SELECT session_id, user_id, device_meta, issued_at, last_seen_at, revoked_at '
                f'FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s AND revoked_at IS NULL ORDER BY last_seen_at DESC',
                (user_id,),
            )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def revoke_session(session_id: str, user_id: int) -> bool:
    """Revoke a session and all refresh tokens tied to it. Returns True if session was found and revoked."""
    conn = _get_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        cur.execute(
            f'UPDATE "{SCHEMA}"."{TABLE}" SET revoked_at = %s WHERE session_id = %s::uuid AND user_id = %s',
            (now, session_id, user_id),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False
        cur.execute(
            f'UPDATE "{SCHEMA}"."{REFRESH_TABLE}" SET revoked_at = COALESCE(revoked_at, %s) WHERE session_id = %s::uuid',
            (now, session_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def revoke_all_sessions_except(user_id: int, except_session_id: Optional[str]) -> int:
    """
    Revoke all sessions for user except the one given. Revokes all refresh tokens in those sessions.
    Returns number of sessions revoked.
    """
    conn = _get_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        if except_session_id:
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" SET revoked_at = %s '
                "WHERE user_id = %s AND revoked_at IS NULL AND session_id != %s::uuid",
                (now, user_id, except_session_id),
            )
        else:
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL',
                (now, user_id),
            )
        count = cur.rowcount or 0
        # Revoke refresh tokens that belong to revoked sessions (or all except those in except_session_id)
        if except_session_id:
            cur.execute(
                f'UPDATE "{SCHEMA}"."{REFRESH_TABLE}" SET revoked_at = COALESCE(revoked_at, %s) '
                "WHERE user_id = %s AND (revoked_at IS NULL) AND (session_id IS NULL OR session_id != %s::uuid)",
                (now, user_id, except_session_id),
            )
        else:
            cur.execute(
                f'UPDATE "{SCHEMA}"."{REFRESH_TABLE}" SET revoked_at = COALESCE(revoked_at, %s) '
                "WHERE user_id = %s AND revoked_at IS NULL",
                (now, user_id),
            )
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
