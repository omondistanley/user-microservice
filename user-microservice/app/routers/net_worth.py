from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from app.core.config import (
    BUDGET_SERVICE_URL,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    EXPENSE_SERVICE_URL,
    INVESTMENT_SERVICE_URL,
)
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/v1", tags=["net-worth"])


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


class NetWorthAssetCreate(BaseModel):
    name: str = Field(..., max_length=255)
    type: str = Field(..., max_length=32)
    value: Decimal = Field(..., ge=0)
    currency: str = Field("USD", min_length=3, max_length=3)


class NetWorthAssetResponse(BaseModel):
    asset_id: UUID
    name: str
    type: str
    value: Decimal
    currency: str


class NetWorthLiabilityCreate(BaseModel):
    name: str = Field(..., max_length=255)
    type: str = Field(..., max_length=32)
    value: Decimal = Field(..., ge=0)
    currency: str = Field("USD", min_length=3, max_length=3)


class NetWorthLiabilityResponse(BaseModel):
    liability_id: UUID
    name: str
    type: str
    value: Decimal
    currency: str


async def _fetch_expense_components(request: Request) -> Dict[str, Any]:
    """Return expense-side net worth components. Never raises 401 — avoids logging the user out when the
    expense service rejects forwarded auth; caller still has investments + manual totals."""
    if not EXPENSE_SERVICE_URL:
        return {
            "assets": {},
            "liabilities": {},
            "metadata": {"warning": "expense_service_not_configured"},
        }
    headers: dict[str, str] = {}
    # Downstream services accept either X-User-Id (set by API gateway) or a Bearer token.
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth
    x_user_id = request.headers.get("X-User-Id") or request.headers.get("x-user-id")
    if x_user_id:
        headers["X-User-Id"] = x_user_id
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["x-request-id"] = str(request_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{EXPENSE_SERVICE_URL}/api/v1/net-worth/components", headers=headers)
    if resp.status_code == 401:
        return {
            "assets": {},
            "liabilities": {},
            "metadata": {"warning": "expense_components_unauthorized"},
        }
    if resp.status_code >= 500:
        return {
            "assets": {},
            "liabilities": {},
            "metadata": {"warning": "expense_service_unavailable"},
        }
    if not resp.is_success:
        return {
            "assets": {},
            "liabilities": {},
            "metadata": {"warning": f"expense_http_{resp.status_code}"},
        }
    data = resp.json()
    if not isinstance(data, dict):
        return {
            "assets": {},
            "liabilities": {},
            "metadata": {"warning": "invalid_expense_payload"},
        }
    return data


async def _fetch_investments_portfolio(request: Request) -> Optional[Dict[str, Any]]:
    if not INVESTMENT_SERVICE_URL:
        return None
    headers: dict[str, str] = {}
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth
    x_user_id = request.headers.get("X-User-Id") or request.headers.get("x-user-id")
    if x_user_id:
        headers["X-User-Id"] = x_user_id
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


async def _fetch_budget_totals(request: Request) -> Optional[Dict[str, Decimal]]:
    """Fetch active budgets and sum amounts for portfolio-style context in net worth."""
    if not BUDGET_SERVICE_URL:
        return None
    headers: dict[str, str] = {}
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth
    x_user_id = request.headers.get("X-User-Id") or request.headers.get("x-user-id")
    if x_user_id:
        headers["X-User-Id"] = x_user_id
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["x-request-id"] = str(request_id)
    try:
        # Budget service caps `page_size` at 100. Page until we have all active budgets.
        budget_total = Decimal("0")
        page = 1
        page_size = 100
        async with httpx.AsyncClient(timeout=15.0) as client:
            while True:
                resp = await client.get(
                    f"{BUDGET_SERVICE_URL}/api/v1/budgets"
                    f"?page={page}&page_size={page_size}&include_inactive=false",
                    headers=headers,
                )
                if not resp.is_success:
                    return None
                data = resp.json()
                items = data.get("items") if isinstance(data, dict) else data
                if not isinstance(items, list):
                    return None
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    budget_total += _to_decimal(it.get("amount"))
                # Stop when we fetched the last page.
                if len(items) < page_size:
                    break
                page += 1
        return {"active_budget_total": budget_total}
    except Exception:
        return None


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _get_manual_totals(user_id: int) -> tuple[Decimal, Decimal]:
    """Return (manual_assets_total, manual_liabilities_total)."""
    manual_assets = Decimal("0")
    manual_liabilities = Decimal("0")
    try:
        conn = _get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(SUM(value), 0) AS total FROM users_db.net_worth_asset WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                manual_assets = _to_decimal(row.get("total"))
            cur.execute(
                "SELECT COALESCE(SUM(value), 0) AS total FROM users_db.net_worth_liability WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                manual_liabilities = _to_decimal(row.get("total"))
        finally:
            conn.close()
    except Exception:
        pass
    return (manual_assets, manual_liabilities)


@router.get("/net-worth/summary", response_model=dict)
async def net_worth_summary(request: Request, current_user: dict = Depends(get_current_user)):
    """Aggregate net-worth components from expense, investments, and manual assets/liabilities."""
    expense_components = await _fetch_expense_components(request)
    investments_portfolio = await _fetch_investments_portfolio(request)
    budget_totals = await _fetch_budget_totals(request)
    user_id = int(current_user["id"])
    manual_assets_total, manual_liabilities_total = _get_manual_totals(user_id)

    assets_in = expense_components.get("assets") or {}
    liabilities_in = expense_components.get("liabilities") or {}

    cash = _to_decimal(assets_in.get("cash"))
    income_window_total = _to_decimal(assets_in.get("income_window_total"))
    budget_total = _to_decimal((budget_totals or {}).get("active_budget_total"))
    debt_placeholder = _to_decimal(liabilities_in.get("spending_obligation"))

    investment_value = Decimal("0")
    if investments_portfolio is not None:
        investment_value = _to_decimal(investments_portfolio.get("total_market_value"))

    assets = {
        "cash": cash,
        "investments": investment_value,
        "income": income_window_total,
        "budgets": budget_total,
        "manual": manual_assets_total,
    }
    liabilities = {
        "debt": Decimal("0"),
        "expenses": debt_placeholder,
        "manual": manual_liabilities_total,
    }

    # Income window is contextual cashflow for the breakdown UI, not balance-sheet assets.
    assets_total = (
        cash + investment_value + budget_total + manual_assets_total
    )
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
    if budget_totals is not None:
        metadata["budget_metadata"] = {"active_budget_total": str(budget_total)}

    warnings: list[str] = []
    if isinstance(exp_meta, dict):
        w = exp_meta.get("warning")
        if w:
            messages = {
                "expense_service_not_configured": "Expense service URL is not configured; cash and income totals may stay at zero.",
                "expense_components_unauthorized": "Expense data could not be loaded (authorization). Sign in again or check the API gateway.",
                "expense_service_unavailable": "Expense service was unavailable; cash and obligations may be incomplete.",
                "invalid_expense_payload": "Expense service returned an unexpected response.",
            }
            warnings.append(messages.get(str(w), f"Expense data notice: {w}"))
    if investments_portfolio is None:
        if INVESTMENT_SERVICE_URL:
            warnings.append(
                "Investment portfolio could not be loaded. From the user microservice, check "
                "INVESTMENT_SERVICE_URL reaches the investments API and JWT is forwarded."
            )
        else:
            warnings.append(
                "INVESTMENT_SERVICE_URL is not set; investment holdings are not included in net worth."
            )
    if budget_totals is None and BUDGET_SERVICE_URL:
        warnings.append("Budget totals could not be loaded; the budgets line may be zero.")
    elif budget_totals is None and not BUDGET_SERVICE_URL:
        pass  # optional service

    return {
        "net_worth": net_worth,
        "assets_total": assets_total,
        "liabilities_total": liabilities_total,
        "assets": assets,
        "liabilities": liabilities,
        "metadata": metadata,
        "warnings": warnings,
    }


@router.get("/net-worth/assets", response_model=List[dict])
async def list_assets(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT asset_id, name, type, value, currency
            FROM users_db.net_worth_asset
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/net-worth/assets", response_model=dict)
async def create_asset(
    payload: NetWorthAssetCreate,
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user["id"])
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users_db.net_worth_asset (user_id, name, type, value, currency)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING asset_id, name, type, value, currency
            """,
            (user_id, payload.name.strip(), payload.type.strip(), payload.value, (payload.currency or "USD").upper()[:3]),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create asset")
        return dict(row)
    finally:
        conn.close()


@router.delete("/net-worth/assets/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: str,
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user["id"])
    try:
        UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset_id")
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM users_db.net_worth_asset WHERE asset_id = %s AND user_id = %s",
            (asset_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Asset not found")
    finally:
        conn.close()


@router.get("/net-worth/liabilities", response_model=List[dict])
async def list_liabilities(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT liability_id, name, type, value, currency
            FROM users_db.net_worth_liability
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/net-worth/liabilities", response_model=dict)
async def create_liability(
    payload: NetWorthLiabilityCreate,
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user["id"])
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users_db.net_worth_liability (user_id, name, type, value, currency)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING liability_id, name, type, value, currency
            """,
            (user_id, payload.name.strip(), payload.type.strip(), payload.value, (payload.currency or "USD").upper()[:3]),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Failed to create liability")
        return dict(row)
    finally:
        conn.close()


@router.delete("/net-worth/liabilities/{liability_id}", status_code=204)
async def delete_liability(
    liability_id: str,
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user["id"])
    try:
        UUID(liability_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid liability_id")
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM users_db.net_worth_liability WHERE liability_id = %s AND user_id = %s",
            (liability_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Liability not found")
    finally:
        conn.close()

