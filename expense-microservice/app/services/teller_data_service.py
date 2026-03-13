"""
Teller enrollment storage: encrypted access_token, CRUD for teller_enrollment table.
Mirrors plaid_data_service pattern.
"""
import logging
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.config import ENCRYPTION_KEY

logger = logging.getLogger(__name__)

SCHEMA = "expenses_db"
TABLE = "teller_enrollment"


def _fernet():
    if not (ENCRYPTION_KEY and ENCRYPTION_KEY.strip()):
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(ENCRYPTION_KEY.strip().encode())
    except Exception as e:
        logger.warning("Fernet init failed: %s", e)
        return None


def encrypt_access_token(access_token: str) -> Optional[str]:
    f = _fernet()
    if not f:
        return None
    try:
        return f.encrypt(access_token.encode()).decode()
    except Exception as e:
        logger.warning("Teller encrypt failed: %s", e)
        return None


def decrypt_access_token(encrypted: str) -> Optional[str]:
    f = _fernet()
    if not f:
        return None
    try:
        return f.decrypt(encrypted.encode()).decode()
    except Exception as e:
        logger.warning("Teller decrypt failed: %s", e)
        return None


class TellerDataService:
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

    def save_enrollment(
        self,
        user_id: int,
        enrollment_id: str,
        access_token_encrypted: str,
        institution_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                INSERT INTO "{SCHEMA}"."{TABLE}"
                (user_id, enrollment_id, access_token_encrypted, institution_name, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (enrollment_id) DO UPDATE SET
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    institution_name = COALESCE(EXCLUDED.institution_name, "{SCHEMA}"."{TABLE}".institution_name),
                    updated_at = now()
                RETURNING id, user_id, enrollment_id, institution_name, created_at
                ''',
                (user_id, enrollment_id, access_token_encrypted, institution_name),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_enrollments(self, user_id: int) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                SELECT id, user_id, enrollment_id, institution_name, created_at
                FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s
                ORDER BY created_at DESC
                ''',
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_enrollment_by_id(self, user_id: int, enrollment_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                SELECT id, user_id, enrollment_id, access_token_encrypted, institution_name
                FROM "{SCHEMA}"."{TABLE}"
                WHERE user_id = %s AND enrollment_id = %s
                ''',
                (user_id, enrollment_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_enrollment_owner(self, enrollment_id: str) -> Optional[int]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'''
                SELECT user_id
                FROM "{SCHEMA}"."{TABLE}"
                WHERE enrollment_id = %s
                LIMIT 1
                ''',
                (enrollment_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return int(row["user_id"])
        finally:
            conn.close()

    def delete_enrollment(self, user_id: int, enrollment_id: str) -> bool:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f'DELETE FROM "{SCHEMA}"."{TABLE}" WHERE user_id = %s AND enrollment_id = %s',
                (user_id, enrollment_id),
            )
            return cur.rowcount > 0
        finally:
            conn.close()
