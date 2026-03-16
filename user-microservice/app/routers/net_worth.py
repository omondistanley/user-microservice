from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from app.core.config import (
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
    user_id = int(current_user["id"])
    manual_assets_total, manual_liabilities_total = _get_manual_totals(user_id)

    assets_in = expense_components.get("assets") or {}
    liabilities_in = expense_components.get("liabilities") or {}

    cash = _to_decimal(assets_in.get("cash"))
    debt_placeholder = _to_decimal(liabilities_in.get("spending_obligation"))

    investment_value = Decimal("0")
    if investments_portfolio is not None:
        investment_value = _to_decimal(investments_portfolio.get("total_market_value"))

    assets = {
        "cash": cash,
        "investments": investment_value,
        "manual": manual_assets_total,
    }
    liabilities = {
        "debt": debt_placeholder,
        "manual": manual_liabilities_total,
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

