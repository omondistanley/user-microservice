from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import ENCRYPTION_KEY, DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


SCHEMA = "investments_db"
TABLE = "alpaca_connection"


def _fernet():
    """Lazy Fernet helper. Returns None if ENCRYPTION_KEY is not set or invalid."""
    if not (ENCRYPTION_KEY and ENCRYPTION_KEY.strip()):
        return None
    try:
        from cryptography.fernet import Fernet

        return Fernet(ENCRYPTION_KEY.strip().encode())
    except Exception:
        return None


def _encrypt(value: str) -> Optional[str]:
    f = _fernet()
    if not f or value is None:
        return None
    try:
        return f.encrypt(value.encode()).decode()
    except Exception:
        return None


def _decrypt(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    f = _fernet()
    if not f:
        return None
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        return None


class AlpacaConnectionService:
    """Manage per-user Alpaca brokerage connections and credentials."""

    def __init__(self, context: Optional[Dict[str, Any]] = None) -> None:
        self.context = context or {
            "user": DB_USER or "postgres",
            "password": DB_PASSWORD or "postgres",
            "host": DB_HOST or "localhost",
            "port": int(DB_PORT) if DB_PORT else 5432,
            "dbname": DB_NAME or "investments_db",
        }

    def _get_connection(self, autocommit: bool = True):
        conn = psycopg2.connect(
            host=self.context["host"],
            port=self.context["port"],
            user=self.context["user"],
            password=self.context["password"],
            dbname=self.context["dbname"],
            cursor_factory=RealDictCursor,
        )
        conn.autocommit = autocommit
        return conn

    def upsert_connection(
        self,
        user_id: int,
        api_key_id: Optional[str],
        api_key_secret: Optional[str],
        alpaca_account_id: Optional[str],
        is_paper: bool,
    ) -> Dict[str, Any]:
        """Create or update a user's Alpaca connection. API keys are stored encrypted when possible."""
        api_key_encrypted = _encrypt(api_key_id) if api_key_id else None
        api_secret_encrypted = _encrypt(api_key_secret) if api_key_secret else None

        now = datetime.now(timezone.utc)
        conn = self._get_connection(autocommit=True)
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO "{SCHEMA}"."{TABLE}"
                    (user_id, alpaca_account_id, api_key_encrypted, api_secret_encrypted, is_paper, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    alpaca_account_id = EXCLUDED.alpaca_account_id,
                    api_key_encrypted = COALESCE(EXCLUDED.api_key_encrypted, "{SCHEMA}"."{TABLE}".api_key_encrypted),
                    api_secret_encrypted = COALESCE(EXCLUDED.api_secret_encrypted, "{SCHEMA}"."{TABLE}".api_secret_encrypted),
                    is_paper = EXCLUDED.is_paper,
                    updated_at = EXCLUDED.updated_at
                RETURNING id, user_id, alpaca_account_id, is_paper, last_sync_at, created_at, updated_at
                """,
                (user_id, alpaca_account_id, api_key_encrypted, api_secret_encrypted, is_paper, now, now),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_connection(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection(autocommit=True)
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                SELECT id, user_id, alpaca_account_id, api_key_encrypted, api_secret_encrypted,
                       is_paper, last_sync_at, created_at, updated_at
                FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s
                ''',
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row)
            # Do not expose decrypted secrets in API responses; keep only encrypted here.
            return {
                "id": data.get("id"),
                "user_id": data.get("user_id"),
                "alpaca_account_id": data.get("alpaca_account_id"),
                "is_paper": data.get("is_paper", True),
                "last_sync_at": data.get("last_sync_at"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            }
        finally:
            conn.close()

    def get_credentials(self, user_id: int) -> Optional[Dict[str, str]]:
        """Return decrypted API key/secret for use by sync jobs. Not exposed via HTTP."""
        conn = self._get_connection(autocommit=True)
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                SELECT api_key_encrypted, api_secret_encrypted, is_paper, alpaca_account_id
                FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s
                ''',
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            api_key = _decrypt(row.get("api_key_encrypted"))
            api_secret = _decrypt(row.get("api_secret_encrypted"))
            if not api_key or not api_secret:
                return None
            return {
                "api_key_id": api_key,
                "api_key_secret": api_secret,
                "alpaca_account_id": row.get("alpaca_account_id") or None,
                "is_paper": bool(row.get("is_paper", True)),
            }
        finally:
            conn.close()

    def list_connection_user_ids(self) -> List[int]:
        """Return all user_ids that have an Alpaca connection (for sync job)."""
        conn = self._get_connection(autocommit=True)
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT user_id FROM "{SCHEMA}"."{TABLE}" ORDER BY user_id',
                (),
            )
            return [int(r["user_id"]) for r in cur.fetchall() if r.get("user_id") is not None]
        finally:
            conn.close()

    def delete_connection(self, user_id: int) -> bool:
        conn = self._get_connection(autocommit=True)
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s',
                (user_id,),
            )
            return cur.rowcount > 0
        finally:
            conn.close()

    def mark_sync(self, user_id: int, when: Optional[datetime] = None) -> None:
        ts = when or datetime.now(timezone.utc)
        conn = self._get_connection(autocommit=True)
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                UPDATE "{SCHEMA}"."{TABLE}"
                SET last_sync_at = %s, updated_at = %s
                WHERE user_id = %s
                ''',
                (ts, ts, user_id),
            )
        finally:
            conn.close()

