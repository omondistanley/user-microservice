"""
Audit logging for security-sensitive user actions.
"""
import ipaddress
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

SCHEMA = "users_db"
TABLE = "audit_log"


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def write_audit_log(
    action: str,
    user_id: int | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Best-effort audit write. Failures are intentionally ignored."""
    normalized_ip = None
    if ip_address:
        try:
            normalized_ip = str(ipaddress.ip_address(ip_address.strip()))
        except ValueError:
            normalized_ip = None

    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{TABLE}" '
            "(user_id, action, ip_address, request_id, details, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                user_id,
                action,
                normalized_ip,
                request_id,
                Json(details) if details is not None else None,
                datetime.now(timezone.utc),
            ),
        )
    except Exception:
        return
    finally:
        conn.close()
