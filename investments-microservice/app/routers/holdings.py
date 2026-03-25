import asyncio
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user_id
from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.models.holdings import HoldingCreate, HoldingListParams, HoldingResponse, HoldingUpdate
from app.resources.holding_resource import HoldingResource
from app.services.service_factory import ServiceFactory
from app.services.market_data_router import get_default_market_data_router
from app.services.news_router import get_news_for_symbol
from app.services.tax_harvesting_scanner import get_lots_for_holding

router = APIRouter(prefix="/api/v1", tags=["holdings"])
logger = logging.getLogger(__name__)


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


def _inv_db_context() -> Dict[str, Any]:
    return {
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "dbname": DB_NAME or "investments_db",
    }


@router.get("/holdings/by-symbol/{symbol}/detail", response_model=dict)
async def holding_symbol_detail(
    symbol: str,
    user_id: int = Depends(get_current_user_id),
):
    """
    Aggregate detail for a symbol across all of the user's holdings.
    Adds live quote, tax lots (when present), and recent headlines when configured.
    Not financial advice. For informational purposes only.
    """
    from decimal import Decimal

    resource = _get_holding_resource()
    from app.models.holdings import HoldingListParams
    items, _ = resource.list(user_id, HoldingListParams(symbol=symbol.upper(), page=1, page_size=100))

    if not items:
        raise HTTPException(status_code=404, detail=f"No holdings found for symbol {symbol.upper()}")

    total_qty = Decimal("0")
    total_cost = Decimal("0")
    account_types: List[str] = []
    role_labels: List[str] = []
    lots_out: List[Dict[str, Any]] = []
    db_ctx = _inv_db_context()

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
        hid = item.get("holding_id")
        created_at = item.get("created_at")
        if hid:
            try:
                for lot in get_lots_for_holding(db_ctx, str(hid), symbol.upper(), qty, cost, created_at):
                    pd = lot.get("purchase_date")
                    lots_out.append(
                        {
                            "lot_id": lot.get("lot_id"),
                            "quantity": float(lot["quantity"]),
                            "cost_per_share": float(lot["cost_per_share"]),
                            "purchase_date": pd.isoformat() if hasattr(pd, "isoformat") else str(pd),
                            "cost_basis": float(lot["cost_basis"]),
                        }
                    )
            except Exception as exc:
                logger.debug("lots for holding %s: %s", hid, exc)

    avg_cost = (total_cost / total_qty) if total_qty > 0 else Decimal("0")
    sym_u = symbol.upper()

    live_quote: Optional[Dict[str, Any]] = None
    market_router = get_default_market_data_router()
    try:
        quote, _, _ = await asyncio.wait_for(
            market_router.get_quote_with_meta(sym_u),
            timeout=4.0,
        )
        if quote and quote.price is not None:
            live_quote = {
                "price": float(quote.price),
                "as_of": quote.as_of.isoformat() if quote.as_of else None,
                "change_pct": float(quote.change_pct) if quote.change_pct is not None else None,
                "provider": quote.provider,
            }
    except Exception as exc:
        logger.debug("quote for %s: %s", sym_u, exc)

    news_headlines: List[Dict[str, Any]] = []
    try:
        loop = asyncio.get_event_loop()
        raw_news = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: get_news_for_symbol(sym_u, 5)),
            timeout=4.0,
        )
        for n in raw_news or []:
            news_headlines.append(
                {
                    "title": (n.get("title") or "")[:200],
                    "url": n.get("url"),
                    "published_at": str(n.get("published_at") or ""),
                    "source_provider": n.get("source_provider"),
                }
            )
    except Exception as exc:
        logger.debug("news for %s: %s", sym_u, exc)

    rmd_context_flag = any(x in ("traditional_ira", "401k") for x in account_types)
    unrealized_pl = None
    if live_quote and total_qty > 0:
        try:
            mval = float(total_qty) * float(live_quote["price"])
            unrealized_pl = round(mval - float(total_cost), 2)
        except Exception:
            unrealized_pl = None

    return {
        "symbol": sym_u,
        "total_quantity": float(total_qty),
        "avg_cost": float(avg_cost),
        "total_cost_basis": float(total_cost),
        "account_types": account_types,
        "role_labels": role_labels,
        "positions_count": len(items),
        "live_quote": live_quote,
        "unrealized_pl": unrealized_pl,
        "tax_lots": lots_out,
        "news_headlines": news_headlines,
        "asset_location_note": (
            "Includes tax-advantaged accounts; consider asset location when adding new positions."
            if ("roth_ira" in account_types or "traditional_ira" in account_types)
            else None
        ),
        "rmd_context_flag": rmd_context_flag,
        "valuation_fit_note": "Fit vs goals is informational; we do not provide security-specific advice.",
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
