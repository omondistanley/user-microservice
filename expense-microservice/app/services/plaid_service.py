"""
Plaid API: link token, exchange public token, fetch transactions.
Uses Plaid REST API via httpx. Access tokens stored encrypted via plaid_data_service.
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV

logger = logging.getLogger(__name__)

# Plaid host by env
PLAID_HOSTS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


def _base_url() -> str:
    return PLAID_HOSTS.get(PLAID_ENV.lower(), PLAID_HOSTS["sandbox"])


def _headers() -> Dict[str, str]:
    return {"Content-Type": "application/json"}


def is_configured() -> bool:
    return bool(PLAID_CLIENT_ID and PLAID_SECRET)


def create_link_token(user_id: int) -> Optional[str]:
    """Create a link_token for Plaid Link. Returns None if Plaid not configured."""
    if not is_configured():
        return None
    url = f"{_base_url()}/link/token/create"
    payload = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "user": {"client_user_id": str(user_id)},
        "client_name": "Expense Tracker",
        "products": ["transactions"],
        "country_codes": ["US"],
        "language": "en",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, json=payload, headers=_headers())
            r.raise_for_status()
            data = r.json()
            return data.get("link_token")
    except Exception as e:
        logger.exception("Plaid link/token/create failed: %s", e)
        return None


def exchange_public_token(public_token: str) -> Optional[Dict[str, Any]]:
    """Exchange public_token for access_token and item_id. Returns dict with access_token, item_id or None."""
    if not is_configured():
        return None
    url = f"{_base_url()}/item/public_token/exchange"
    payload = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "public_token": public_token,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, json=payload, headers=_headers())
            r.raise_for_status()
            data = r.json()
            return {"access_token": data.get("access_token"), "item_id": data.get("item_id")}
    except Exception as e:
        logger.exception("Plaid item/public_token/exchange failed: %s", e)
        return None


def fetch_transactions(
    access_token: str,
    date_from: date,
    date_to: date,
) -> List[Dict[str, Any]]:
    """Fetch transactions for date range. Returns list of transaction objects (debits as positive amounts)."""
    if not is_configured():
        return []
    url = f"{_base_url()}/transactions/get"
    payload = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "access_token": access_token,
        "start_date": date_from.isoformat(),
        "end_date": date_to.isoformat(),
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(url, json=payload, headers=_headers())
            r.raise_for_status()
            data = r.json()
            return data.get("transactions") or []
    except Exception as e:
        logger.exception("Plaid transactions/get failed: %s", e)
        return []


def item_get(access_token: str) -> Optional[Dict[str, Any]]:
    """Get item details including institution_id. Returns item dict or None."""
    if not is_configured():
        return None
    url = f"{_base_url()}/item/get"
    payload = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "access_token": access_token,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url, json=payload, headers=_headers())
            r.raise_for_status()
            return r.json().get("item")
    except Exception as e:
        logger.warning("Plaid item/get failed: %s", e)
        return None
