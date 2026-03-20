"""
Execution service for portfolio rebalance automation.

Consumes planner output and:
  - places Alpaca sell orders immediately (sell-now)
  - places Alpaca buy orders the next day (buy-next-day)
  - sends in-app notifications (modal opened on click; payload includes why_lines/changes)

Live trading safety:
  - if Alpaca connection is live (is_paper=False), orders are rejected unless LIVE_TRADING_ENABLED is true.
"""

from __future__ import annotations

import os
import logging
import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, INTERNAL_API_KEY, USER_SERVICE_INTERNAL_URL
from app.services.alpaca_broker_client import create_order as alpaca_create_order
from app.services.alpaca_broker_client import get_account as alpaca_get_account
from app.services.alpaca_connection_service import AlpacaConnectionService
from app.services.market_data_router import get_default_market_data_router
from app.services.market_data_models import Quote

logger = logging.getLogger("rebalance_execution")


_DB_CONTEXT = {
    "host": DB_HOST or "localhost",
    "port": int(DB_PORT) if DB_PORT else 5432,
    "user": DB_USER or "postgres",
    "password": DB_PASSWORD or "postgres",
    "dbname": DB_NAME or "investments_db",
}


def _env_bool(name: str, default: bool = False) -> bool:
    val = (os.environ.get(name) or "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "y", "on")


def _live_trading_enabled() -> bool:
    # Allow import-less fallback so earlier phases can compile even if config isn't updated yet.
    try:
        from app.core import config as cfg  # type: ignore

        if hasattr(cfg, "LIVE_TRADING_ENABLED"):
            return bool(getattr(cfg, "LIVE_TRADING_ENABLED"))
    except Exception:
        pass
    return _env_bool("LIVE_TRADING_ENABLED", default=False)


def _user_service_internal_base_url() -> str:
    # Different services use this env/config name; keep it tolerant.
    return (USER_SERVICE_INTERNAL_URL or "").rstrip("/")


def _internal_notification_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if INTERNAL_API_KEY:
        headers["x-internal-api-key"] = INTERNAL_API_KEY
    return headers


async def _get_quotes_for_symbols(symbols: List[str]) -> Dict[str, Quote]:
    router = get_default_market_data_router()
    out: Dict[str, Quote] = {}
    # Small, deterministic concurrency (avoid hammering providers in a single rebalance).
    sem = asyncio.Semaphore(5)

    async def _one(sym: str) -> None:
        async with sem:
            quote, _, _ = await router.get_quote_with_meta(sym)
            out[sym.upper()] = quote

    await asyncio.gather(*[_one(s) for s in symbols if s])
    return out


@dataclass(frozen=True)
class OrderExecutionResult:
    symbol: str
    side: str
    order_type: str
    qty: Decimal
    limit_price: Optional[Decimal]
    alpaca_response: Dict[str, Any]


class RebalanceExecutionService:
    """
    Execution wrapper around Alpaca Trading API + in-app notification creation.
    """

    def __init__(self) -> None:
        self._alpaca_conn_svc = AlpacaConnectionService(context=_DB_CONTEXT)

    def _check_live_trading_guard(self, is_paper: bool) -> None:
        if bool(is_paper):
            return
        # Live account: require explicit enable.
        if not _live_trading_enabled():
            raise RuntimeError(
                "Live trading is disabled. Set LIVE_TRADING_ENABLED=true to allow placing orders on live Alpaca accounts."
            )

    async def execute_sell_phase(
        self,
        *,
        user_id: int,
        scenario: str,
        rebalance_session_id: str,
        why_lines: List[str],
        sell_orders: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Place sell orders immediately and return a payload suitable for persisting notification content.
        """
        if not sell_orders:
            return {"executed": True, "sell_results": []}

        creds = self._alpaca_conn_svc.get_credentials(user_id)
        if not creds:
            raise RuntimeError("Alpaca not connected for this user.")

        is_paper = bool(creds.get("is_paper", True))
        self._check_live_trading_guard(is_paper)

        results: List[OrderExecutionResult] = []
        for so in sell_orders:
            sym = str(so.get("symbol") or "").upper()
            if not sym:
                continue
            qty = Decimal(str(so.get("qty") or "0"))
            if qty <= 0:
                continue
            order_type = str(so.get("order_type") or "market").lower()
            limit_price: Optional[Decimal] = None
            if order_type == "limit":
                # For deterministic sell limit, use quote + small premium.
                # Quote lookup is best-effort (skip to market if quote fails).
                try:
                    quotes = await _get_quotes_for_symbols([sym])
                    q = quotes.get(sym)
                    if q and getattr(q, "price", None) is not None:
                        price = Decimal(str(q.price))
                        offset = Decimal("0.005")  # +0.5%
                        limit_price = price * (Decimal("1") + offset)
                except Exception:
                    limit_price = None
                    order_type = "market"

            resp = alpaca_create_order(
                api_key_id=creds["api_key_id"],
                api_key_secret=creds["api_key_secret"],
                is_paper=is_paper,
                symbol=sym,
                qty=float(qty),
                side="sell",
                order_type=order_type,
                time_in_force="day",
                limit_price=float(limit_price) if limit_price is not None else None,
            )
            results.append(
                OrderExecutionResult(
                    symbol=sym,
                    side="sell",
                    order_type=order_type,
                    qty=qty,
                    limit_price=limit_price,
                    alpaca_response=resp,
                )
            )

        notification = await self._notify_user(
            user_id=user_id,
            notification_type="recommendation",
            title="Rebalance: sell phase executed",
            body="Portfolio rebalance sell orders were executed. Review the rule trace in the details modal.",
            payload={
                "rebalance_session_id": rebalance_session_id,
                "scenario": scenario,
                "phase": "sell_done",
                "why_lines": why_lines,
                "changes": {
                    "sell_orders": [
                        {
                            "symbol": r.symbol,
                            "qty": str(r.qty),
                            "order_type": r.order_type,
                            "limit_price": str(r.limit_price) if r.limit_price is not None else None,
                            "alpaca_order_id": r.alpaca_response.get("id"),
                            "status": r.alpaca_response.get("status"),
                        }
                        for r in results
                    ],
                },
                "executed": True,
                "auto_open_modal": False,
            },
        )

        return {
            "executed": True,
            "sell_results": [r.__dict__ for r in results],
            "notification": notification,
        }

    async def execute_buy_phase(
        self,
        *,
        user_id: int,
        scenario: str,
        rebalance_session_id: str,
        why_lines: List[str],
        buy_orders: List[Dict[str, Any]],
        cash_reserve_pct: Decimal = Decimal("0.01"),
        limit_offset_pct: Decimal = Decimal("0.005"),  # -0.5% limit buy
    ) -> Dict[str, Any]:
        """
        Place buy orders using available cash and planner allocation weights.
        """
        if not buy_orders:
            return {"executed": True, "buy_results": []}

        creds = self._alpaca_conn_svc.get_credentials(user_id)
        if not creds:
            raise RuntimeError("Alpaca not connected for this user.")

        is_paper = bool(creds.get("is_paper", True))
        self._check_live_trading_guard(is_paper)

        # Fetch cash from Alpaca.
        account = alpaca_get_account(
            api_key_id=creds["api_key_id"],
            api_key_secret=creds["api_key_secret"],
            is_paper=is_paper,
        )
        cash_raw = None
        if isinstance(account, dict):
            cash_raw = account.get("cash") or account.get("cash_available") or account.get("buying_power") or 0

        cash = Decimal(str(cash_raw or "0"))
        if cash <= 0:
            return {
                "executed": False,
                "error": "No cash available for buying.",
                "buy_results": [],
            }

        cash_to_spend = cash * (Decimal("1") - cash_reserve_pct)

        # Fetch quotes once for deterministic qty calculations and limit pricing.
        symbols = [str(b.get("symbol") or "").upper() for b in buy_orders if b.get("symbol")]
        quotes = await _get_quotes_for_symbols(symbols)

        alloc_sum = sum(_safe_decimal(b.get("allocation_weight")) for b in buy_orders)
        if alloc_sum <= 0:
            # If planner weights are missing, fall back to equal allocation.
            alloc_sum = Decimal(str(len(buy_orders) or 1))
            for b in buy_orders:
                b["allocation_weight"] = "1"

        results: List[OrderExecutionResult] = []
        for bo in buy_orders:
            sym = str(bo.get("symbol") or "").upper()
            if not sym:
                continue
            quote = quotes.get(sym)
            if not quote or getattr(quote, "price", None) is None:
                continue

            price = Decimal(str(quote.price))
            if price <= 0:
                continue

            weight = _safe_decimal(bo.get("allocation_weight"))
            notional = cash_to_spend * (weight / alloc_sum)
            if notional <= 0:
                continue

            conf = _safe_decimal(bo.get("confidence"))
            order_type = str(bo.get("order_type") or ("market" if conf >= Decimal("0.75") else "limit")).lower()

            limit_price: Optional[Decimal] = None
            if order_type == "limit":
                limit_price = price * (Decimal("1") - limit_offset_pct)
                if limit_price <= 0:
                    order_type = "market"
                    limit_price = None

            # Quantity is based on limit_price if limit order, otherwise quote price.
            px = limit_price if limit_price is not None else price
            qty = notional / px
            if qty <= 0:
                continue

            resp = alpaca_create_order(
                api_key_id=creds["api_key_id"],
                api_key_secret=creds["api_key_secret"],
                is_paper=is_paper,
                symbol=sym,
                qty=float(qty),
                side="buy",
                order_type=order_type,
                time_in_force="day",
                limit_price=float(limit_price) if limit_price is not None else None,
            )
            results.append(
                OrderExecutionResult(
                    symbol=sym,
                    side="buy",
                    order_type=order_type,
                    qty=qty,
                    limit_price=limit_price,
                    alpaca_response=resp,
                )
            )

        notification = await self._notify_user(
            user_id=user_id,
            notification_type="recommendation",
            title="Rebalance: buy phase executed",
            body="Portfolio rebalance buy orders were executed. Review the rule trace in the details modal.",
            payload={
                "rebalance_session_id": rebalance_session_id,
                "scenario": scenario,
                "phase": "buy_done",
                "why_lines": why_lines,
                "changes": {
                    "buy_orders": [
                        {
                            "symbol": r.symbol,
                            "qty": str(r.qty),
                            "order_type": r.order_type,
                            "limit_price": str(r.limit_price) if r.limit_price is not None else None,
                            "alpaca_order_id": r.alpaca_response.get("id"),
                            "status": r.alpaca_response.get("status"),
                        }
                        for r in results
                    ],
                    "cash_used": str(cash_to_spend),
                },
                "executed": True,
                "auto_open_modal": False,
            },
        )

        return {
            "executed": True,
            "buy_results": [r.__dict__ for r in results],
            "notification": notification,
        }

    async def _notify_user(
        self,
        *,
        user_id: int,
        notification_type: str,
        title: str,
        body: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        base = _user_service_internal_base_url()
        if not base:
            logger.info("Notification skipped: USER_SERVICE_INTERNAL_URL not configured.")
            return {"skipped": True}

        url = f"{base}/internal/v1/notifications"
        headers = _internal_notification_headers()
        # Best-effort; execution should not fail the whole job due to UI notification.
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(url, json={
                    "user_id": user_id,
                    "type": notification_type,
                    "title": title,
                    "body": body,
                    "payload": payload,
                }, headers=headers)
            if resp.status_code >= 400:
                return {"skipped": True, "status_code": resp.status_code, "detail": resp.text}
            return resp.json() if resp.content else {"ok": True}
        except Exception as e:
            logger.warning("rebalance notify failed: %s", e)
            return {"skipped": True, "error": str(e)}


# Local helper for safe decimal parsing without importing planner module internals.
def _safe_decimal(x: Any) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")

