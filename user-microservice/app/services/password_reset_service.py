"""
Password reset token creation and validation. Always return generic success from forgot-password.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    RESET_TOKEN_EXPIRE_HOURS,
    APP_BASE_URL,
)
from app.core.security import hash_password
from app.services.email_service import send_email

SCHEMA = "users_db"
TABLE = "password_reset_token"


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset_token(email: str) -> None:
    """
    If user exists: create reset token, store hash, send email with link.
    Always returns without error (no email enumeration).
    """
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute('SELECT id FROM users_db."user" WHERE email = %s', (email,))
        row = cur.fetchone()
        if not row:
            return
        user_id = row["id"]
        raw = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS)
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{TABLE}" (user_id, token_hash, expires_at) VALUES (%s, %s, %s)',
            (user_id, token_hash, expires_at),
        )
        conn.commit()
        link = f"{APP_BASE_URL.rstrip('/')}/reset-password?token={raw}"
        body = f"Use this link to reset your password (valid for {RESET_TOKEN_EXPIRE_HOURS} hour(s)):\n\n{link}\n\nIf you did not request this, ignore this email."
        send_email(email, "Reset your password", body)
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def validate_and_consume_reset_token(token: str) -> Optional[int]:
    """
    Validate token: find by hash, check expiry. Return user_id and delete token (one-time use).
    Returns None if invalid or expired.
    """
    token_hash = _hash_token(token)
    conn = _get_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            f'SELECT id, user_id, expires_at FROM "{SCHEMA}"."{TABLE}" WHERE token_hash = %s',
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            return None
        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            cur.execute(f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE id = %s', (row["id"],))
            conn.commit()
            return None
        user_id = row["user_id"]
        cur.execute(f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE id = %s', (row["id"],))
        conn.commit()
        return user_id
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def set_password(user_id: int, new_password: str) -> None:
    """Update user password by id."""
    password_hash = hash_password(new_password)
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            'UPDATE users_db."user" SET password_hash = %s, modified_at = %s WHERE id = %s',
            (password_hash, datetime.now(timezone.utc), user_id),
        )
    finally:
        conn.close()
