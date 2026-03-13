from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user_id
from app.services.holdings_data_service import HoldingsDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/api/v1", tags=["portfolio"])


def _get_data_service() -> HoldingsDataService:
    ds = ServiceFactory.get_service("HoldingsDataService")
    if not isinstance(ds, HoldingsDataService):
        raise RuntimeError("HoldingsDataService not available")
    return ds


@router.get("/portfolio/value", response_model=dict)
async def portfolio_value(
    user_id: int = Depends(get_current_user_id),
):
    """Aggregate holdings into a simple portfolio valuation snapshot.

    For now, market value is approximated using quantity * avg_cost for each
    position. This will be replaced by quote-driven valuation in later phases.
    """
    ds = _get_data_service()
    rows = ds.list_all_holdings_for_user(user_id)

    total_cost_basis = Decimal("0")
    total_market_value = Decimal("0")

    positions: list[dict] = []
    for row in rows:
        quantity = Decimal(str(row.get("quantity") or "0"))
        avg_cost = Decimal(str(row.get("avg_cost") or "0"))
        position_cost = quantity * avg_cost
        total_cost_basis += position_cost
        # Until real quotes exist, treat cost basis as a proxy for market value.
        total_market_value += position_cost
        positions.append(
            {
                "symbol": row.get("symbol"),
                "quantity": quantity,
                "avg_cost": avg_cost,
                "currency": row.get("currency", "USD"),
                "cost_basis": position_cost,
            }
        )

    unrealized_pl = total_market_value - total_cost_basis

    return {
        "total_market_value": total_market_value,
        "total_cost_basis": total_cost_basis,
        "unrealized_pl": unrealized_pl,
        "positions": positions,
        "metadata": {
            "valuation_source": "holdings_cost_basis",
        },
    }

