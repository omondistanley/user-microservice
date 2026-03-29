"""Per-user settings service for currency, theme, and notification preferences."""
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
            f'SELECT user_id, default_currency, theme_preference, '
            f'push_notifications_enabled, email_notifications_enabled, updated_at, active_household_id '
            f'FROM "{SCHEMA}"."{TABLE}" '
            "WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        now = datetime.now(timezone.utc)
        cur.execute(
            f'INSERT INTO "{SCHEMA}"."{TABLE}" '
            "(user_id, default_currency, theme_preference, push_notifications_enabled, email_notifications_enabled, updated_at, active_household_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, NULL) "
            "ON CONFLICT (user_id) DO UPDATE SET updated_at = EXCLUDED.updated_at "
            "RETURNING user_id, default_currency, theme_preference, push_notifications_enabled, email_notifications_enabled, updated_at, active_household_id",
            (user_id, "USD", "system", True, False, now),
        )
        created = cur.fetchone()
        return dict(created) if created else {
            "user_id": user_id,
            "default_currency": "USD",
            "theme_preference": "system",
            "push_notifications_enabled": True,
            "email_notifications_enabled": False,
            "updated_at": now,
            "active_household_id": None,
        }
    finally:
        conn.close()


def update_user_settings(
    user_id: int,
    *,
    default_currency: str | None = None,
    theme_preference: str | None = None,
    push_notifications_enabled: bool | None = None,
    email_notifications_enabled: bool | None = None,
) -> dict[str, Any]:
    currency = str(default_currency or "").strip().upper() if default_currency is not None else None
    if currency is not None and len(currency) != 3:
        raise ValueError("default_currency must be a 3-letter code")
    if theme_preference is not None and theme_preference not in {"light", "dark", "system"}:
        raise ValueError("theme_preference must be one of: light, dark, system")
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        cur.execute(
            f"""
            INSERT INTO "{SCHEMA}"."{TABLE}"
            (user_id, default_currency, theme_preference, push_notifications_enabled, email_notifications_enabled, updated_at, active_household_id)
            VALUES (%s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT (user_id)
            DO UPDATE SET
                default_currency = EXCLUDED.default_currency,
                theme_preference = EXCLUDED.theme_preference,
                push_notifications_enabled = EXCLUDED.push_notifications_enabled,
                email_notifications_enabled = EXCLUDED.email_notifications_enabled,
                updated_at = EXCLUDED.updated_at
            RETURNING user_id, default_currency, theme_preference, push_notifications_enabled, email_notifications_enabled, updated_at, active_household_id
            """,
            (
                user_id,
                currency or "USD",
                theme_preference or "system",
                True if push_notifications_enabled is None else bool(push_notifications_enabled),
                False if email_notifications_enabled is None else bool(email_notifications_enabled),
                now,
            ),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        return {
            "user_id": user_id,
            "default_currency": currency or "USD",
            "theme_preference": theme_preference or "system",
            "push_notifications_enabled": True if push_notifications_enabled is None else bool(push_notifications_enabled),
            "email_notifications_enabled": False if email_notifications_enabled is None else bool(email_notifications_enabled),
            "updated_at": now,
            "active_household_id": None,
        }
    finally:
        conn.close()
