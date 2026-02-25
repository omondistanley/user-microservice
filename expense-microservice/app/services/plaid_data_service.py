"""
Plaid item storage: encrypted access_token, CRUD for plaid_item table.
"""
import logging
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import ENCRYPTION_KEY

logger = logging.getLogger(__name__)

SCHEMA = "expenses_db"
TABLE = "plaid_item"


def _fernet():
    """Lazy Fernet for encrypt/decrypt. Returns None if ENCRYPTION_KEY not set."""
    if not (ENCRYPTION_KEY and ENCRYPTION_KEY.strip()):
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(ENCRYPTION_KEY.strip().encode())
    except Exception as e:
        logger.warning("Fernet init failed: %s", e)
        return None


def encrypt_access_token(access_token: str) -> Optional[str]:
    """Encrypt access_token for storage. Returns None if encryption not available (store as-is not recommended)."""
    f = _fernet()
    if not f:
        return None
    try:
        return f.encrypt(access_token.encode()).decode()
    except Exception as e:
        logger.warning("Encrypt failed: %s", e)
        return None


def decrypt_access_token(encrypted: str) -> Optional[str]:
    """Decrypt stored access_token."""
    f = _fernet()
    if not f:
        return None
    try:
        return f.decrypt(encrypted.encode()).decode()
    except Exception as e:
        logger.warning("Decrypt failed: %s", e)
        return None


class PlaidDataService:
    def __init__(self, context: Dict[str, Any]):
        self.context = context

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

    def save_plaid_item(
        self,
        user_id: int,
        item_id: str,
        access_token_encrypted: str,
        institution_id: Optional[str] = None,
        institution_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                INSERT INTO "{SCHEMA}"."{TABLE}"
                (user_id, item_id, access_token_encrypted, institution_id, institution_name, updated_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (item_id) DO UPDATE SET
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    institution_id = COALESCE(EXCLUDED.institution_id, "expenses_db"."plaid_item".institution_id),
                    institution_name = COALESCE(EXCLUDED.institution_name, "expenses_db"."plaid_item".institution_name),
                    updated_at = now()
                RETURNING id, user_id, item_id, institution_id, institution_name, created_at
                ''',
                (user_id, item_id, access_token_encrypted, institution_id, institution_name),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_plaid_items(self, user_id: int) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                SELECT id, user_id, item_id, institution_id, institution_name, created_at
                FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s
                ORDER BY created_at DESC
                ''',
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_plaid_item_by_item_id(self, user_id: int, item_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                SELECT id, user_id, item_id, access_token_encrypted, institution_id, institution_name
                FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s AND item_id = %s
                ''',
                (user_id, item_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_plaid_item(self, user_id: int, item_id: str) -> bool:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s AND item_id = %s',
                (user_id, item_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()
