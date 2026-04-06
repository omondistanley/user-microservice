"""
Plaid API: link token, exchange public token, fetch transactions.
Uses Plaid REST API via httpx. Access tokens stored encrypted via plaid_data_service.
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import (
    PLAID_CLIENT_ID,
    PLAID_ENABLE_RECURRING_TRANSACTIONS,
    PLAID_ENV,
    PLAID_HOSTED_COMPLETION_REDIRECT_URI,
    PLAID_SECRET,
    PLAID_WEBHOOK_URL,
)

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


def _link_token_products() -> List[str]:
    """Transactions only by default; optional Recurring (extra Plaid fee per account/month)."""
    p = ["transactions"]
    if PLAID_ENABLE_RECURRING_TRANSACTIONS:
        p.append("recurring_transactions")
    return p


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
        "products": _link_token_products(),
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


def create_hosted_link_session(
    user_id: int,
    completion_redirect_uri: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Create a Hosted Link session. Returns { hosted_link_url, link_token, expiration } or None.

    Notes:
    - Plaid does not guarantee delivering public_token via redirect; primary delivery is via webhook.
    - We return link_token so the client can later call /link/token/get (fallback path) to obtain public_token.
    """
    if not is_configured():
        return None
    url = f"{_base_url()}/link/token/create"
    hosted_link: Dict[str, Any] = {}
    redirect = (completion_redirect_uri or PLAID_HOSTED_COMPLETION_REDIRECT_URI or "").strip()
    if redirect:
        hosted_link["completion_redirect_uri"] = redirect
    payload: Dict[str, Any] = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "user": {"client_user_id": str(user_id)},
        "client_name": "Expense Tracker",
        "products": _link_token_products(),
        "country_codes": ["US"],
        "language": "en",
        "hosted_link": hosted_link,
    }
    if PLAID_WEBHOOK_URL:
        payload["webhook"] = PLAID_WEBHOOK_URL
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, json=payload, headers=_headers())
            r.raise_for_status()
            data = r.json() or {}
            hosted_url = data.get("hosted_link_url")
            link_token = data.get("link_token")
            if not hosted_url or not link_token:
                return None
            return {
                "hosted_link_url": hosted_url,
                "link_token": link_token,
                "expiration": data.get("expiration"),
            }
    except Exception as e:
        logger.exception("Plaid hosted link/token/create failed: %s", e)
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


def link_token_get(link_token: str) -> Optional[Dict[str, Any]]:
    """
    Call /link/token/get to fetch session metadata and, if available, public_token(s).
    Returns raw Plaid response dict (or None on error).
    """
    if not is_configured():
        return None
    url = f"{_base_url()}/link/token/get"
    payload = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "link_token": link_token,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, json=payload, headers=_headers())
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.exception("Plaid link/token/get failed: %s", e)
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
        "options": {
            "include_personal_finance_category": True,
        },
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


def fetch_accounts(access_token: str) -> List[Dict[str, Any]]:
    """
    List accounts for an Item (/accounts/get). No Balance product — metadata only;
    typically no extra Plaid product charge vs /accounts/balance/get.
    """
    if not is_configured():
        return []
    url = f"{_base_url()}/accounts/get"
    payload = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "access_token": access_token,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, json=payload, headers=_headers())
            r.raise_for_status()
            data = r.json() or {}
            return data.get("accounts") or []
    except Exception as e:
        logger.warning("Plaid accounts/get failed: %s", e)
        return []
