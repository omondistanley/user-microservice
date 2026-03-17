"""
Thin client for Alpaca Trading API (accounts and positions).
Used by the Alpaca sync job to fetch positions and map to holdings.
Base URLs: paper https://paper-api.alpaca.markets, live https://api.alpaca.markets
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

PAPER_BASE = "https://paper-api.alpaca.markets"
LIVE_BASE = "https://api.alpaca.markets"


def get_positions(
    api_key_id: str,
    api_key_secret: str,
    is_paper: bool = True,
    timeout: float = 15.0,
) -> List[Dict[str, Any]]:
    """
    Fetch all open positions for the account.
    Returns list of position dicts with symbol, qty, market_value, cost_basis, etc.
    """
    base = PAPER_BASE if is_paper else LIVE_BASE
    url = f"{base.rstrip('/')}/v2/positions"
    headers = {
        "APCA-API-KEY-ID": api_key_id,
        "APCA-API-SECRET-KEY": api_key_secret,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        return []
    return data


def get_account(
    api_key_id: str,
    api_key_secret: str,
    is_paper: bool = True,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Fetch account info (id, status, etc.). Used to validate credentials and get account_id."""
    base = PAPER_BASE if is_paper else LIVE_BASE
    url = f"{base.rstrip('/')}/v2/account"
    headers = {
        "APCA-API-KEY-ID": api_key_id,
        "APCA-API-SECRET-KEY": api_key_secret,
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def create_order(
    api_key_id: str,
    api_key_secret: str,
    is_paper: bool,
    symbol: str,
    qty: float,
    side: str,
    order_type: str = "market",
    time_in_force: str = "day",
    limit_price: Optional[float] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """
    Place an order via Alpaca POST /v2/orders.
    side: "buy" | "sell", order_type: "market" | "limit", time_in_force: "day" | "gtc" | etc.
    Returns the order response from Alpaca.
    """
    base = PAPER_BASE if is_paper else LIVE_BASE
    url = f"{base.rstrip('/')}/v2/orders"
    headers = {
        "APCA-API-KEY-ID": api_key_id,
        "APCA-API-SECRET-KEY": api_key_secret,
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {
        "symbol": symbol.strip().upper(),
        "qty": str(qty),
        "side": side.lower(),
        "type": order_type.lower(),
        "time_in_force": time_in_force.lower(),
    }
    if order_type.lower() == "limit" and limit_price is not None:
        body["limit_price"] = str(limit_price)
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=body)
    resp.raise_for_status()
    return resp.json()


def position_to_holding_row(
    user_id: int,
    position: Dict[str, Any],
    external_id: str,
) -> Dict[str, Any]:
    """
    Map an Alpaca position to our holding row (symbol, quantity, avg_cost, source, external_id).
    Alpaca position: qty (str), symbol, cost_basis (optional), market_value, avg_entry_price, etc.
    """
    symbol = (position.get("symbol") or "").strip().upper()
    if not symbol:
        return {}
    qty = position.get("qty")
    if qty is None:
        return {}
    try:
        quantity = Decimal(str(qty))
    except Exception:
        return {}
    if quantity <= 0:
        return {}
    cost_basis = position.get("cost_basis")
    avg_entry = position.get("avg_entry_price")
    if cost_basis is not None and quantity and quantity != 0:
        try:
            avg_cost = Decimal(str(cost_basis)) / quantity
        except Exception:
            avg_cost = Decimal("0")
    elif avg_entry is not None:
        try:
            avg_cost = Decimal(str(avg_entry))
        except Exception:
            avg_cost = Decimal("0")
    else:
        avg_cost = Decimal("0")
    return {
        "user_id": user_id,
        "symbol": symbol,
        "quantity": quantity,
        "avg_cost": avg_cost,
        "currency": "USD",
        "exchange": position.get("exchange") or None,
        "notes": None,
        "source": "alpaca",
        "external_id": external_id,
    }
