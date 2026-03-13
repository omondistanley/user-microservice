from decimal import Decimal
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.core.config import EXPENSE_SERVICE_URL, INVESTMENT_SERVICE_URL

router = APIRouter(prefix="/api/v1", tags=["net-worth"])


async def _fetch_expense_components(request: Request) -> Dict[str, Any]:
    if not EXPENSE_SERVICE_URL:
        raise HTTPException(status_code=503, detail="Expense service not configured")
    headers: dict[str, str] = {}
    auth = request.headers.get("authorization")
    if auth:
        headers["authorization"] = auth
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["x-request-id"] = str(request_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{EXPENSE_SERVICE_URL}/api/v1/net-worth/components", headers=headers)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if resp.status_code >= 500:
        raise HTTPException(status_code=502, detail="Expense service unavailable")
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail="Failed to fetch expense components")
    data = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Invalid expense components payload")
    return data


async def _fetch_investments_portfolio(request: Request) -> Optional[Dict[str, Any]]:
    if not INVESTMENT_SERVICE_URL:
        return None
    headers: dict[str, str] = {}
    auth = request.headers.get("authorization")
    if auth:
        headers["authorization"] = auth
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["x-request-id"] = str(request_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{INVESTMENT_SERVICE_URL}/api/v1/portfolio/value", headers=headers)
        except Exception:
            return None
    if not resp.is_success:
        return None
    data = resp.json()
    if not isinstance(data, dict):
        return None
    return data


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


@router.get("/net-worth/summary", response_model=dict)
async def net_worth_summary(request: Request):
    """Aggregate net-worth components from expense and investments services.

    - Assets: cash balances from expense service, investment portfolio value.
    - Liabilities: spending/debt placeholder from expense service.
    - Net worth: sum(assets) - sum(liabilities).
    """
    expense_components = await _fetch_expense_components(request)
    investments_portfolio = await _fetch_investments_portfolio(request)

    assets_in = expense_components.get("assets") or {}
    liabilities_in = expense_components.get("liabilities") or {}

    cash = _to_decimal(assets_in.get("cash"))
    # Do NOT treat income/expense flow totals as assets or liabilities.
    debt_placeholder = _to_decimal(liabilities_in.get("spending_obligation"))

    investment_value = Decimal("0")
    if investments_portfolio is not None:
        investment_value = _to_decimal(investments_portfolio.get("total_market_value"))

    assets = {
        "cash": cash,
        "investments": investment_value,
    }
    liabilities = {
        "debt": debt_placeholder,
    }

    assets_total = sum(assets.values(), Decimal("0"))
    liabilities_total = sum(liabilities.values(), Decimal("0"))
    net_worth = assets_total - liabilities_total

    metadata: dict[str, Any] = {
        "expense_source": "expense-microservice",
    }
    exp_meta = expense_components.get("metadata")
    if isinstance(exp_meta, dict):
        metadata["expense_metadata"] = exp_meta
    if investments_portfolio is not None:
        metadata["investments_metadata"] = investments_portfolio.get("metadata")

    return {
        "net_worth": net_worth,
        "assets_total": assets_total,
        "liabilities_total": liabilities_total,
        "assets": assets,
        "liabilities": liabilities,
        "metadata": metadata,
    }

