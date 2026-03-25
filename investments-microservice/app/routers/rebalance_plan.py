"""
Rebalancing plan endpoint.

Returns a step-by-step informational summary of how a user could address portfolio drift.
Account-type-conditional: wash-sale language only shown for taxable accounts.
Not financial advice. This is informational only.
"""
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.core.dependencies import get_current_user_id
from app.services.holdings_data_service import HoldingsDataService
from app.services.service_factory import ServiceFactory
from app.services.sector_exposure_service import aggregate_by_sector
from app.services.market_data_router import MarketDataRouter, get_default_market_data_router

import asyncio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["rebalance-plan"])


def _get_data_service() -> HoldingsDataService:
    ds = ServiceFactory.get_service("HoldingsDataService")
    if not isinstance(ds, HoldingsDataService):
        raise RuntimeError("HoldingsDataService not available")
    return ds


def _get_market_router() -> MarketDataRouter:
    return get_default_market_data_router()


def _db_context() -> Dict[str, Any]:
    return {
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "dbname": DB_NAME or "investments_db",
    }


def _tax_note(account_type: str, symbol: str, gain_loss: float) -> str:
    """Return account-type-conditional tax framing."""
    at = (account_type or "taxable").lower()
    if at in ("traditional_ira", "roth_ira", "401k", "hsa"):
        acct_label = {"traditional_ira": "Traditional IRA", "roth_ira": "Roth IRA", "401k": "401(k)", "hsa": "HSA"}.get(at, at)
        return f"No capital gains tax applies within {acct_label} accounts. Wash-sale rules do not apply here."
    # Taxable account
    gl_type = "gain" if gain_loss >= 0 else "loss"
    return (
        f"This would realise an estimated ${abs(gain_loss):.2f} {gl_type} in your taxable account. "
        "Tax impact depends on your full tax situation — consult a tax professional."
    )


def _wash_sale_note(account_type: str, symbol: str) -> Optional[str]:
    at = (account_type or "taxable").lower()
    if at in ("traditional_ira", "roth_ira", "401k", "hsa"):
        return None  # No wash-sale in tax-advantaged accounts
    return (
        f"Wash-sale consideration (taxable accounts): if you sell {symbol} at a loss and repurchase "
        "a substantially identical security within 30 days before or after the sale, the loss deduction "
        "may be disallowed. This is informational — consult a tax professional."
    )


@router.get("/portfolio/rebalance-plan", response_model=dict)
async def get_rebalance_plan(
    user_id: int = Depends(get_current_user_id),
    ds: HoldingsDataService = Depends(_get_data_service),
    market_router: MarketDataRouter = Depends(_get_market_router),
):
    """
    Informational step-by-step rebalancing summary.
    Account-type-conditional tax notes. Not a recommendation to trade.
    """
    rows = ds.list_all_holdings_for_user(user_id)
    if not rows:
        return {
            "steps": [],
            "summary": "Add holdings to generate a rebalancing plan.",
            "disclaimer": "This shows one possible approach to address portfolio drift based on your stated targets. It is not a recommendation to trade. Not financial advice.",
        }

    # Build positions with live values
    positions = []
    total_value = Decimal("0")
    for row in rows:
        sym = (row.get("symbol") or "").strip().upper()
        qty = Decimal(str(row.get("quantity") or "0"))
        avg_cost = Decimal(str(row.get("avg_cost") or "0"))
        cost_basis = qty * avg_cost
        market_value = cost_basis
        try:
            quote, _, _ = await asyncio.wait_for(
                market_router.get_quote_with_meta(sym), timeout=4.0
            )
            if quote and quote.price and quote.price > 0:
                market_value = qty * Decimal(str(quote.price))
        except Exception:
            pass
        unrealised = market_value - cost_basis
        positions.append({
            "symbol": sym,
            "quantity": qty,
            "avg_cost": avg_cost,
            "market_value": market_value,
            "unrealised_pl": unrealised,
            "account_type": (row.get("account_type") or "taxable"),
        })
        total_value += market_value

    if total_value == 0:
        return {
            "steps": [],
            "summary": "Portfolio value is zero — add market prices to generate a plan.",
            "disclaimer": "This shows one possible approach to address portfolio drift. Not financial advice.",
        }

    # Sector breakdown
    context = _db_context()
    pos_for_sector = [{"symbol": p["symbol"], "value": p["market_value"]} for p in positions]
    sector_data = aggregate_by_sector(context, pos_for_sector)
    sectors = sector_data.get("sectors") or []

    # Find most overweight and most underweight positions
    positions_sorted_by_weight = sorted(
        positions,
        key=lambda p: float(p["market_value"] / total_value),
        reverse=True
    )

    steps = []

    # Step 1: Identify overweight position to trim
    if len(positions_sorted_by_weight) >= 2:
        top = positions_sorted_by_weight[0]
        top_weight = float(top["market_value"] / total_value * 100)
        if top_weight > 35:
            gain_loss = float(top["unrealised_pl"])
            tax_note = _tax_note(top["account_type"], top["symbol"], gain_loss)
            wash_note = _wash_sale_note(top["account_type"], top["symbol"])
            step = {
                "step": 1,
                "type": "trim",
                "title": f"One approach: reduce {top['symbol']} position",
                "detail": (
                    f"{top['symbol']} represents {top_weight:.1f}% of your portfolio. "
                    f"Trimming to ~25% would free approximately "
                    f"${float((top['market_value'] - total_value * Decimal('0.25'))):.2f} "
                    "to redeploy toward underweight areas."
                ),
                "tax_note": tax_note,
            }
            if wash_note:
                step["wash_sale_note"] = wash_note
            steps.append(step)

    # Step 2: Identify underweight sectors
    if sectors:
        underweight = sorted(
            [s for s in sectors if float(s.get("weight") or s.get("pct") or 0) < 10],
            key=lambda s: float(s.get("weight") or s.get("pct") or 0)
        )
        if underweight:
            uw = underweight[0]
            sector_name = uw.get("sector") or uw.get("name") or "Unknown"
            sector_pct = float(uw.get("weight") or uw.get("pct") or 0)
            steps.append({
                "step": 2,
                "type": "add_exposure",
                "title": f"One approach: add {sector_name} exposure",
                "detail": (
                    f"Your {sector_name} allocation is approximately {sector_pct:.1f}% of your portfolio. "
                    "Adding a position in this sector could address this gap if it aligns with your stated targets. "
                    "This is informational — your targets may differ."
                ),
            })

    # Step 3: Summary
    steps.append({
        "step": len(steps) + 1,
        "type": "review",
        "title": "Review and decide",
        "detail": (
            "These steps are one possible approach to address portfolio drift. "
            "Consider your tax situation, time horizon, goals, and risk tolerance before acting. "
            "Each step has a checkbox — mark completion to update your holdings."
        ),
    })

    return {
        "steps": steps,
        "total_portfolio_value": float(total_value),
        "positions_count": len(positions),
        "disclaimer": (
            "This shows one possible approach to address portfolio drift based on your stated targets. "
            "It is not a recommendation to trade. Consider your own tax situation, goals, risk tolerance, "
            "and account types before acting. Not financial advice."
        ),
    }
