"""
Refresh token storage and validation. Uses hashlib.sha256 for token_hash.
"""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

SCHEMA = "users_db"
TABLE = "refresh_token"


@dataclass(frozen=True)
class RefreshTokenValidationResult:
    status: Literal["ok", "invalid", "reused"]
    user_id: int | None = None
    email: str | None = None
    family_id: str | None = None


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


def create_refresh_token(user_id: int, family_id: str | None = None) -> str:
    """Generate a new refresh token, store its hash in DB, return the raw token."""
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    token_family_id = family_id or str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{TABLE}" (user_id, token_hash, expires_at, family_id) VALUES (%s, %s, %s, %s)',
            (user_id, token_hash, expires_at, token_family_id),
        )
        return raw
    finally:
        conn.close()


def revoke_all_refresh_tokens(user_id: int, conn=None) -> int:
    """Revoke all active refresh tokens for a user. Returns number of rows touched."""
    own_conn = conn is None
    if own_conn:
        conn = _get_connection()
        conn.autocommit = True
    try:
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        cur.execute(
            f'UPDATE "{SCHEMA}"."{TABLE}" '
            "SET revoked_at = COALESCE(revoked_at, %s) "
            "WHERE user_id = %s AND revoked_at IS NULL",
            (now, user_id),
        )
        return cur.rowcount or 0
    finally:
        if own_conn and conn:
            conn.close()


def revoke_refresh_token_family(user_id: int, family_id: str, conn=None) -> int:
    """Revoke all active refresh tokens in a single family for a user."""
    own_conn = conn is None
    if own_conn:
        conn = _get_connection()
        conn.autocommit = True
    try:
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        cur.execute(
            f'UPDATE "{SCHEMA}"."{TABLE}" '
            "SET revoked_at = COALESCE(revoked_at, %s) "
            "WHERE user_id = %s AND family_id = %s::uuid AND revoked_at IS NULL",
            (now, user_id, family_id),
        )
        return cur.rowcount or 0
    finally:
        if own_conn and conn:
            conn.close()


def validate_refresh_token(token: str) -> RefreshTokenValidationResult:
    """
    Validate and consume a refresh token.

    - status="ok": valid token consumed; caller should issue a new refresh token in same family.
    - status="invalid": token missing/expired/revoked.
    - status="reused": consumed token was used again; token family is revoked
      (or all tokens when family metadata is unavailable).
    """
    token_hash = _hash_token(token)
    conn = _get_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            f'SELECT id, user_id, expires_at, consumed_at, revoked_at, family_id '
            f'FROM "{SCHEMA}"."{TABLE}" WHERE token_hash = %s FOR UPDATE',
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            return RefreshTokenValidationResult(status="invalid")

        user_id = row["user_id"]
        now = datetime.now(timezone.utc)

        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now >= expires_at:
            cur.execute(
                f'UPDATE "{SCHEMA}"."{TABLE}" '
                "SET revoked_at = COALESCE(revoked_at, %s) "
                "WHERE id = %s",
                (now, row["id"]),
            )
            conn.commit()
            return RefreshTokenValidationResult(status="invalid", user_id=user_id)

        if row.get("consumed_at") is not None:
            # Refresh token reuse detected: revoke token family (fallback to all if family missing).
            family_id = row.get("family_id")
            if family_id is not None:
                revoke_refresh_token_family(user_id, str(family_id), conn=conn)
            else:
                revoke_all_refresh_tokens(user_id, conn=conn)
            conn.commit()
            return RefreshTokenValidationResult(
                status="reused",
                user_id=user_id,
                family_id=str(family_id) if family_id is not None else None,
            )

        if row.get("revoked_at") is not None:
            conn.commit()
            return RefreshTokenValidationResult(status="invalid", user_id=user_id)

        cur.execute(
            f'UPDATE "{SCHEMA}"."{TABLE}" '
            "SET consumed_at = %s WHERE id = %s AND consumed_at IS NULL",
            (now, row["id"]),
        )
        cur.execute(
            'SELECT email FROM users_db."user" WHERE id = %s',
            (user_id,),
        )
        user_row = cur.fetchone()
        conn.commit()
        if not user_row or not user_row.get("email"):
            return RefreshTokenValidationResult(status="invalid", user_id=user_id)
        return RefreshTokenValidationResult(
            status="ok",
            user_id=user_id,
            email=user_row["email"],
            family_id=str(row["family_id"]) if row.get("family_id") is not None else None,
        )
    except Exception:
        conn.rollback()
        return RefreshTokenValidationResult(status="invalid")
    finally:
        conn.close()
