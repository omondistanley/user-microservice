from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import INTERNAL_API_KEY
from app.routers.plaid import PlaidSyncBody, plaid_sync
from app.routers.teller import TellerSyncBody, teller_sync
from app.services.expense_data_service import ExpenseDataService
from app.services.goal_data_service import GoalDataService
from app.services.plaid_data_service import PlaidDataService
from app.services.service_factory import ServiceFactory
from app.services.teller_data_service import TellerDataService

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def _validate_internal_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    if INTERNAL_API_KEY and x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def _get_data_service() -> ExpenseDataService:
    ds = ServiceFactory.get_service("ExpenseDataService")
    if not isinstance(ds, ExpenseDataService):
        raise RuntimeError("ExpenseDataService not available")
    return ds


def _get_plaid_data_service() -> PlaidDataService:
    svc = ServiceFactory.get_service("PlaidDataService")
    if not isinstance(svc, PlaidDataService):
        raise RuntimeError("PlaidDataService not available")
    return svc


def _get_teller_data_service() -> TellerDataService:
    svc = ServiceFactory.get_service("TellerDataService")
    if not isinstance(svc, TellerDataService):
        raise RuntimeError("TellerDataService not available")
    return svc


def _get_goal_data_service() -> GoalDataService:
    svc = ServiceFactory.get_service("GoalDataService")
    if not isinstance(svc, GoalDataService):
        raise RuntimeError("GoalDataService not available")
    return svc


class ProviderWebhookEvent(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    event_id: str = Field(..., min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)


def _pick_nested(payload: dict[str, Any], keys: list[str]) -> Optional[str]:
    for key in keys:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    data_obj = payload.get("data")
    if isinstance(data_obj, dict):
        for key in keys:
            val = data_obj.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


@router.delete("/users/{user_id}/expenses", response_model=dict, include_in_schema=False)
async def purge_user_expenses(
    user_id: int,
    request: Request,
    _: None = Depends(_validate_internal_key),
):
    ds = _get_data_service()
    result = ds.purge_user_data(user_id)
    request_id = str(getattr(request.state, "request_id", "") or "")
    return {
        "user_id": user_id,
        "request_id": request_id or None,
        "result": result,
    }


@router.post("/providers/webhook-event", include_in_schema=False)
async def process_provider_webhook_event(
    body: ProviderWebhookEvent,
    _: None = Depends(_validate_internal_key),
):
    provider = body.provider.strip().lower()
    payload = body.payload or {}

    if provider == "plaid":
        item_id = _pick_nested(payload, ["item_id", "itemId"])
        if not item_id:
            return {"ok": False, "provider": provider, "reason": "missing_item_id"}
        pds = _get_plaid_data_service()
        owner_user_id: Optional[int] = pds.get_plaid_item_owner(str(item_id))
        if owner_user_id is None:
            return {"ok": False, "provider": provider, "reason": "item_not_linked"}
        result = await plaid_sync(body=PlaidSyncBody(), user_id=owner_user_id)
        return {"ok": True, "provider": provider, "user_id": owner_user_id, "sync": result}

    if provider == "teller":
        enrollment_id = _pick_nested(payload, ["enrollment_id", "enrollmentId"])
        if not enrollment_id:
            return {"ok": False, "provider": provider, "reason": "missing_enrollment_id"}
        tds = _get_teller_data_service()
        owner_user_id = tds.get_enrollment_owner(str(enrollment_id))
        if owner_user_id is None:
            return {"ok": False, "provider": provider, "reason": "enrollment_not_linked"}
        result = await teller_sync(body=TellerSyncBody(), user_id=owner_user_id)
        return {"ok": True, "provider": provider, "user_id": owner_user_id, "sync": result}

    return {"ok": False, "provider": provider, "reason": "unsupported_provider"}


@router.get("/finance-context", response_model=dict)
async def internal_finance_context(
    user_id: int,
    window_months: int = 6,
    _: None = Depends(_validate_internal_key),
):
    """
    Internal finance context endpoint used by the investments microservice for
    goal/horizon-aware rebalance planning without needing a user JWT.
    """
    from datetime import date, timedelta
    from decimal import Decimal

    ds = _get_data_service()
    gs = _get_goal_data_service()

    end = date.today()
    start = end - timedelta(days=min(365, window_months * 31))

    # Cashflow summary.
    income_total: Decimal = Decimal("0")
    expense_total: Decimal = Decimal("0")
    data_fresh = True
    try:
        income_total = ds.get_income_total(user_id=user_id, date_from=start.isoformat(), date_to=end.isoformat())
        expense_total = ds.get_expense_total(user_id=user_id, date_from=start.isoformat(), date_to=end.isoformat())
    except Exception:
        data_fresh = False

    surplus = income_total - expense_total
    savings_rate: Optional[float] = None
    if income_total and income_total > 0:
        savings_rate = float((income_total - expense_total) / income_total)

    # Goals.
    active_goals_count = 0
    goal_horizon_months: Optional[int] = None
    goals_behind_count = 0

    try:
        goals_rows, _total = gs.list_goals(user_id, active_only=True, limit=50, offset=0)
        active_goals_count = len(goals_rows)

        if goals_rows:
            min_months: Optional[int] = None
            behind_count = 0
            for g in goals_rows:
                target_date_str = g.get("target_date")
                if target_date_str:
                    try:
                        target = date.fromisoformat(str(target_date_str).replace("Z", "").split("T")[0])
                        delta_days = (target - end).days
                        months = max(0, delta_days // 30) if delta_days > 0 else 0
                        if min_months is None or months < min_months:
                            min_months = months
                    except Exception:
                        pass

                goal_id = g.get("goal_id")
                if goal_id:
                    prog = gs.get_progress(goal_id=goal_id, user_id=user_id)
                    if prog:
                        target_amt = float(prog.get("target_amount") or 0)
                        current_amt = float(prog.get("current_amount") or 0)
                        if target_amt > 0 and current_amt < target_amt * 0.85:
                            behind_count += 1

            goal_horizon_months = min_months
            goals_behind_count = behind_count
    except Exception:
        # Missing/invalid goal data shouldn't block recommendations; treat as stale.
        data_fresh = False

    return {
        "savings_rate": savings_rate,
        "surplus": float(surplus) if surplus is not None else None,
        "income_total": float(income_total) if income_total is not None else None,
        "expense_total": float(expense_total) if expense_total is not None else None,
        "active_goals_count": int(active_goals_count or 0),
        "goal_horizon_months": goal_horizon_months,
        "goals_behind": goals_behind_count > 0,
        "goals_behind_count": int(goals_behind_count or 0),
        "budget_over": False,
        "data_fresh": bool(data_fresh),
    }
