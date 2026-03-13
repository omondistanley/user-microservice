"""
Teller API: list accounts, list transactions.
Uses mTLS (certificate + key) for authentication.
Access tokens are stored encrypted via teller_data_service.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import TELLER_APP_ID, TELLER_CERT_PATH, TELLER_KEY_PATH

logger = logging.getLogger(__name__)

TELLER_BASE = "https://api.teller.io"


def is_configured() -> bool:
    return bool(TELLER_APP_ID)


def _cert():
    """Return (cert, key) tuple for mTLS, or None if not configured."""
    if TELLER_CERT_PATH and TELLER_KEY_PATH:
        return (TELLER_CERT_PATH, TELLER_KEY_PATH)
    return None


def _client() -> httpx.Client:
    cert = _cert()
    if cert:
        return httpx.Client(cert=cert, timeout=30.0)
    return httpx.Client(timeout=30.0)


def list_accounts(access_token: str) -> List[Dict[str, Any]]:
    """List all accounts for a given Teller access token."""
    try:
        with _client() as client:
            r = client.get(
                f"{TELLER_BASE}/accounts",
                auth=(access_token, ""),
            )
            r.raise_for_status()
            return r.json() or []
    except Exception as e:
        logger.exception("Teller list_accounts failed: %s", e)
        return []


def list_transactions(
    access_token: str,
    account_id: str,
    from_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List transactions for a Teller account. Optionally paginate with from_id."""
    params: Dict[str, str] = {"count": "100"}
    if from_id:
        params["from_id"] = from_id
    try:
        with _client() as client:
            r = client.get(
                f"{TELLER_BASE}/accounts/{account_id}/transactions",
                auth=(access_token, ""),
                params=params,
            )
            r.raise_for_status()
            return r.json() or []
    except Exception as e:
        logger.exception("Teller list_transactions failed for account %s: %s", account_id, e)
        return []


def get_account(access_token: str, account_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single account's details."""
    try:
        with _client() as client:
            r = client.get(
                f"{TELLER_BASE}/accounts/{account_id}",
                auth=(access_token, ""),
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("Teller get_account failed: %s", e)
        return None
