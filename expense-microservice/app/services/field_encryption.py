"""
Sprint 5 — Field-level encryption for sensitive expense fields.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256) from the
`cryptography` package — the same library already used by Plaid token storage.

Encrypted fields: expense.description (free-text merchant notes).
The `amount` column stores a NUMERIC in the DB and is NOT encrypted because:
  - It participates in aggregation queries (SUM, AVG) server-side.
  - It is already protected by row-level access control (user_id filter on every query).
  - Encrypting it would require fetching all rows to compute totals.

Design:
  - encrypt_field(plaintext) → "fernet:<base64>" sentinel prefix to distinguish
    encrypted from legacy plaintext values.
  - decrypt_field(value) → original string; passthrough for unencrypted values
    (backwards-compatible with existing rows).
  - If ENCRYPTION_KEY is not set, both functions are no-ops (dev/test mode).

The service layer (ExpenseDataService._insert_expense_using_conn) calls
encrypt_field() on the description before INSERT.
The resource/router layer calls decrypt_field() on description when reading.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("field_encryption")

_ENCRYPTED_PREFIX = "fernet:"


def _get_key() -> Optional[bytes]:
    key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    return key.encode() if isinstance(key, str) else key


def encrypt_field(value: Optional[str]) -> Optional[str]:
    """
    Encrypt a string field value. Returns None if input is None.
    If ENCRYPTION_KEY is not set, returns the plaintext unchanged (no-op).
    """
    if value is None:
        return None
    key = _get_key()
    if not key:
        return value
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key)
        ciphertext = f.encrypt(value.encode("utf-8")).decode("utf-8")
        return f"{_ENCRYPTED_PREFIX}{ciphertext}"
    except Exception as exc:
        logger.warning("field_encrypt_failed: %s — storing plaintext", exc)
        return value


def decrypt_field(value: Optional[str]) -> Optional[str]:
    """
    Decrypt a field value that may have been encrypted by encrypt_field().
    Passthrough for None or values without the sentinel prefix (legacy rows).
    If ENCRYPTION_KEY is not set, returns the value unchanged.
    """
    if value is None:
        return None
    if not value.startswith(_ENCRYPTED_PREFIX):
        return value  # unencrypted legacy value — pass through
    key = _get_key()
    if not key:
        # Key removed after data was encrypted — cannot decrypt; return sentinel
        logger.warning("field_decrypt_no_key: returning raw encrypted value")
        return value
    try:
        from cryptography.fernet import Fernet, InvalidToken
        f = Fernet(key)
        ciphertext = value[len(_ENCRYPTED_PREFIX):]
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.warning("field_decrypt_failed: %s — returning raw value", exc)
        return value
