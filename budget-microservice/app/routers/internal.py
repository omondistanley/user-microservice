from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.config import INTERNAL_API_KEY
from app.services.budget_data_service import BudgetDataService
from app.services.service_factory import ServiceFactory

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def _validate_internal_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    if INTERNAL_API_KEY and x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def _get_data_service() -> BudgetDataService:
    ds = ServiceFactory.get_service("BudgetDataService")
    if not isinstance(ds, BudgetDataService):
        raise RuntimeError("BudgetDataService not available")
    return ds


@router.delete("/users/{user_id}/budgets", response_model=dict, include_in_schema=False)
async def purge_user_budgets(
    user_id: int,
    request: Request,
    _: None = Depends(_validate_internal_key),
):
    ds = _get_data_service()
    result = ds.purge_user_budgets(user_id)
    request_id = str(getattr(request.state, "request_id", "") or "")
    return {
        "user_id": user_id,
        "request_id": request_id or None,
        "result": result,
    }
