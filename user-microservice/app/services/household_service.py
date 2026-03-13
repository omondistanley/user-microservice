"""
Household and membership operations for Phase 3.
"""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

SCHEMA = "users_db"


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def create_household(owner_user_id: int, name: str) -> dict[str, Any]:
    conn = _get_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            f'INSERT INTO "{SCHEMA}".household (owner_user_id, name, created_at, updated_at) '
            "VALUES (%s, %s, now(), now()) RETURNING household_id, owner_user_id, name, created_at, updated_at",
            (owner_user_id, name),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise ValueError("Failed to create household")
        household_id = row["household_id"]
        cur.execute(
            f'INSERT INTO "{SCHEMA}".household_member (household_id, user_id, role, status, created_at, updated_at) '
            "VALUES (%s, %s, 'owner', 'active', now(), now())",
            (household_id, owner_user_id),
        )
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_households_for_user(user_id: int) -> list[dict[str, Any]]:
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT h.household_id, h.owner_user_id, h.name, h.created_at, h.updated_at,
                   hm.role, hm.status
            FROM "{SCHEMA}".household h
            JOIN "{SCHEMA}".household_member hm ON hm.household_id = h.household_id
            WHERE hm.user_id = %s AND hm.status = 'active'
            ORDER BY h.name
            """,
            (user_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_household(household_id: str, user_id: int) -> dict[str, Any] | None:
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT h.household_id, h.owner_user_id, h.name, h.created_at, h.updated_at,
                   hm.role, hm.status
            FROM "{SCHEMA}".household h
            JOIN "{SCHEMA}".household_member hm ON hm.household_id = h.household_id
            WHERE h.household_id = %s AND hm.user_id = %s AND hm.status = 'active'
            """,
            (household_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def is_active_member(household_id: str, user_id: int) -> bool:
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT 1 FROM "{SCHEMA}".household_member '
            "WHERE household_id = %s AND user_id = %s AND status = 'active'",
            (household_id, user_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def get_member_role(household_id: str, user_id: int) -> str | None:
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT role FROM "{SCHEMA}".household_member '
            "WHERE household_id = %s AND user_id = %s AND status = 'active'",
            (household_id, user_id),
        )
        row = cur.fetchone()
        return row["role"] if row else None
    finally:
        conn.close()


def add_member(household_id: str, invited_user_id: int, inviter_user_id: int, role: str = "member") -> dict[str, Any]:
    if not is_active_member(household_id, inviter_user_id):
        raise PermissionError("Not a member of this household")
    if get_member_role(household_id, inviter_user_id) != "owner":
        raise PermissionError("Only owner can add members")
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'INSERT INTO "{SCHEMA}".household_member (household_id, user_id, role, status, invited_by_user_id, created_at, updated_at) '
            "VALUES (%s, %s, %s, 'active', %s, now(), now()) "
            "ON CONFLICT (household_id, user_id) DO UPDATE SET role = EXCLUDED.role, status = 'active', updated_at = now() "
            "RETURNING household_id, user_id, role, status, created_at",
            (household_id, invited_user_id, role, inviter_user_id),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}
    except psycopg2.IntegrityError:
        conn.rollback()
        raise ValueError("User not found or invalid household")
    finally:
        conn.close()


def update_member(household_id: str, member_user_id: int, actor_user_id: int, role: str | None = None, status: str | None = None) -> dict[str, Any]:
    if get_member_role(household_id, actor_user_id) != "owner":
        raise PermissionError("Only owner can update members")
    conn = _get_connection()
    try:
        cur = conn.cursor()
        updates = []
        vals = []
        if role is not None:
            updates.append("role = %s")
            vals.append(role)
        if status is not None:
            updates.append("status = %s")
            vals.append(status)
        if not updates:
            row = _get_member_row(conn, household_id, member_user_id)
            return dict(row) if row else {}
        updates.append("updated_at = now()")
        vals.extend([household_id, member_user_id])
        cur.execute(
            f'UPDATE "{SCHEMA}".household_member SET ' + ", ".join(updates) + " WHERE household_id = %s AND user_id = %s RETURNING household_id, user_id, role, status, updated_at",
            vals,
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}
    finally:
        conn.close()


def _get_member_row(conn, household_id: str, user_id: int) -> dict | None:
    cur = conn.cursor()
    cur.execute(
        f'SELECT household_id, user_id, role, status, updated_at FROM "{SCHEMA}".household_member WHERE household_id = %s AND user_id = %s',
        (household_id, user_id),
    )
    return cur.fetchone()


def remove_member(household_id: str, member_user_id: int, actor_user_id: int) -> bool:
    actor_role = get_member_role(household_id, actor_user_id)
    if actor_role is None:
        raise PermissionError("Not a member of this household")
    if actor_user_id != member_user_id and actor_role != "owner":
        raise PermissionError("Only owner can remove other members")
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'UPDATE "{SCHEMA}".household_member SET status = %s, updated_at = now() WHERE household_id = %s AND user_id = %s',
            ("removed", household_id, member_user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_user_scope(user_id: int) -> dict[str, Any]:
    """Return user_id and active_household_id from user_settings. Used by expense/budget to resolve scope."""
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT user_id, active_household_id FROM "{SCHEMA}".user_settings WHERE user_id = %s',
            (user_id,),
        )
        row = cur.fetchone()
        if row:
            return {"user_id": row["user_id"], "active_household_id": str(row["active_household_id"]) if row.get("active_household_id") else None}
        return {"user_id": user_id, "active_household_id": None}
    finally:
        conn.close()


def list_members(household_id: str, user_id: int) -> list[dict[str, Any]]:
    if not is_active_member(household_id, user_id):
        raise PermissionError("Not a member of this household")
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT household_id, user_id, role, status, invited_by_user_id, created_at, updated_at '
            f'FROM "{SCHEMA}".household_member WHERE household_id = %s AND status = %s ORDER BY role DESC, user_id',
            (household_id, "active"),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def set_active_household(user_id: int, household_id: str | None) -> None:
    if household_id is not None and not is_active_member(household_id, user_id):
        raise ValueError("Not a member of this household")
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'UPDATE "{SCHEMA}".user_settings SET active_household_id = %s, updated_at = now() WHERE user_id = %s',
            (household_id, user_id),
        )
        if cur.rowcount == 0:
            cur.execute(
                f'INSERT INTO "{SCHEMA}".user_settings (user_id, default_currency, updated_at, active_household_id) '
                "VALUES (%s, 'USD', now(), %s)",
                (user_id, household_id),
            )
        conn.commit()
    finally:
        conn.close()
