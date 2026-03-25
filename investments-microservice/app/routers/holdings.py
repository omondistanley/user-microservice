from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user_id
from app.models.holdings import HoldingCreate, HoldingListParams, HoldingResponse, HoldingUpdate
from app.resources.holding_resource import HoldingResource
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["holdings"])


def _get_holding_resource() -> HoldingResource:
    res = ServiceFactory.get_service("HoldingResource")
    if res is None:
        raise RuntimeError("HoldingResource not available")
    return res


@router.get("/holdings", response_model=dict)
async def list_holdings(
    user_id: int = Depends(get_current_user_id),
    household_id: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    hh_uuid = None
    if household_id:
        try:
            hh_uuid = UUID(household_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid household_id")
    resource = _get_holding_resource()
    params = HoldingListParams(
        household_id=hh_uuid,
        symbol=symbol,
        page=page,
        page_size=page_size,
    )
    items, total = resource.list(user_id, params)
    return {"items": items, "total": total}


@router.post("/holdings", response_model=HoldingResponse)
async def create_holding(
    payload: HoldingCreate,
    user_id: int = Depends(get_current_user_id),
):
    resource = _get_holding_resource()
    return resource.create(user_id, payload)


@router.get("/holdings/{holding_id}", response_model=HoldingResponse)
async def get_holding(
    holding_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        hid = UUID(holding_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid holding id")
    resource = _get_holding_resource()
    return resource.get_by_id(hid, user_id)


@router.patch("/holdings/{holding_id}", response_model=HoldingResponse)
async def update_holding(
    holding_id: str,
    payload: HoldingUpdate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        hid = UUID(holding_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid holding id")
    resource = _get_holding_resource()
    return resource.update(hid, user_id, payload)


@router.get("/holdings/by-symbol/{symbol}/detail", response_model=dict)
async def holding_symbol_detail(
    symbol: str,
    user_id: int = Depends(get_current_user_id),
):
    """
    Aggregate detail for a symbol across all of the user's holdings.
    Returns quantity, cost basis, account types, and role label.
    Not financial advice. For informational purposes only.
    """
    from decimal import Decimal
    resource = _get_holding_resource()
    from app.models.holdings import HoldingListParams
    items, _ = resource.list(user_id, HoldingListParams(symbol=symbol.upper(), page=1, page_size=100))

    if not items:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No holdings found for symbol {symbol.upper()}")

    total_qty = Decimal("0")
    total_cost = Decimal("0")
    account_types = []
    role_labels = []

    for item in items:
        qty = Decimal(str(item.get("quantity") or 0))
        cost = Decimal(str(item.get("avg_cost") or 0))
        total_qty += qty
        total_cost += qty * cost
        at = item.get("account_type")
        rl = item.get("role_label")
        if at and at not in account_types:
            account_types.append(at)
        if rl and rl not in role_labels:
            role_labels.append(rl)

    avg_cost = (total_cost / total_qty) if total_qty > 0 else Decimal("0")

    return {
        "symbol": symbol.upper(),
        "total_quantity": float(total_qty),
        "avg_cost": float(avg_cost),
        "total_cost_basis": float(total_cost),
        "account_types": account_types,
        "role_labels": role_labels,
        "positions_count": len(items),
        "disclaimer": "Not financial advice. For informational purposes only.",
    }


@router.delete("/holdings/{holding_id}", status_code=204)
async def delete_holding(
    holding_id: str,
    user_id: int = Depends(get_current_user_id),
):
    try:
        hid = UUID(holding_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid holding id")
    resource = _get_holding_resource()
    resource.delete(hid, user_id)
