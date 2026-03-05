"""
Email verification: create token on register, verify via GET /verify-email?token=...
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
    APP_BASE_URL,
)
from app.services.email_service import send_email

VERIFICATION_EXPIRE_HOURS = 24


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


def create_verification_token(user_id: int, email: str) -> None:
    """Generate token, store hash and expiry on user row, send verification email."""
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_EXPIRE_HOURS)
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            'UPDATE users_db."user" SET verification_token_hash = %s, verification_token_expires_at = %s WHERE id = %s',
            (token_hash, expires_at, user_id),
        )
        link = f"{APP_BASE_URL.rstrip('/')}/verify-email?token={raw}"
        body = f"Verify your email by clicking this link (valid for {VERIFICATION_EXPIRE_HOURS} hours):\n\n{link}\n\nIf you did not create an account, ignore this email."
        send_email(email, "Verify your email", body)
    finally:
        conn.close()


def verify_email_token(token: str) -> bool:
    """
    Validate token, set email_verified_at and clear token. Returns True if verified.
    """
    token_hash = _hash_token(token)
    conn = _get_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            'SELECT id, verification_token_expires_at FROM users_db."user" WHERE verification_token_hash = %s',
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            return False
        expires_at = row["verification_token_expires_at"]
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and datetime.now(timezone.utc) >= expires_at:
            cur.execute(
                'UPDATE users_db."user" SET verification_token_hash = NULL, verification_token_expires_at = NULL WHERE id = %s',
                (row["id"],),
            )
            conn.commit()
            return False
        cur.execute(
            'UPDATE users_db."user" SET email_verified_at = %s, verification_token_hash = NULL, verification_token_expires_at = NULL WHERE id = %s',
            (datetime.now(timezone.utc), row["id"]),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()
