"""
Account lifecycle operations.
"""
import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def delete_user_account(user_id: int) -> bool:
    """
    Delete user account row. Related token rows are removed via FK cascade.
    Returns True when a user row was deleted.
    """
    conn = _get_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute('DELETE FROM users_db."user" WHERE id = %s', (user_id,))
        deleted = (cur.rowcount or 0) > 0
        if deleted:
            conn.commit()
        else:
            conn.rollback()
        return deleted
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()
