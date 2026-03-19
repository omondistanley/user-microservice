"""Interactive demo API — requires demo JWT."""
from datetime import date
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth_demo import COOKIE_NAME, verify_demo_token
from app.config import (
    DEMO_MAX_BUDGETS_PER_SESSION,
    DEMO_MAX_EXPENSES_PER_SESSION,
    DEMO_MAX_GOALS_PER_SESSION,
    DEMO_MAX_INCOME_PER_SESSION,
)
from app.db import (
    add_budget,
    add_expense,
    add_goal,
    add_income,
    count_budgets,
    count_expenses,
    count_goals,
    count_income,
    get_expense,
    get_goal,
    get_income,
    list_budgets,
    list_expenses,
    list_goals,
    list_income,
    WATCH_SESSION_ID,
    category_spend_for_month,
    total_spend_for_month,
    touch_activity,
    set_insights_feedback,
    update_budget,
    update_expense,
    update_goal,
    update_income,
)
from app.limiter_util import limiter

router = APIRouter(prefix="/api/demo", tags=["demo-api"])


def _session_id(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME)
    payload = verify_demo_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Demo session required")
    sid = str(payload["sid"])
    # Prevent any interaction with the watch-only seed rows.
    if sid == WATCH_SESSION_ID:
        raise HTTPException(status_code=403, detail="Demo access denied")
    return sid


class ExpenseIn(BaseModel):
    amount: float = Field(gt=0, le=999999)
    description: str = Field(min_length=1, max_length=500)
    category: str = Field(default="Other", max_length=64)
    expense_date: Optional[str] = None


_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


class BudgetIn(BaseModel):
    month: str = Field(min_length=7, max_length=7)
    category: str = Field(default="Other", max_length=64)
    limit: float = Field(gt=0, le=999999)


def _validate_month(month: str) -> str:
    m = (month or "").strip()
    if not _MONTH_RE.match(m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    return m


def _validate_date(d: Optional[str]) -> str:
    v = (d or "").strip()
    if not v:
        return date.today().isoformat()
    if not _DATE_RE.match(v):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    return v


class InsightsFeedbackIn(BaseModel):
    decision: str = Field(default="ignore", max_length=16)


class RecommendationsRunIn(BaseModel):
    month: Optional[str] = None
    risk_tolerance: str = Field(default="balanced", max_length=32)
    industries: str = Field(default="", max_length=256)
    use_budget: bool = Field(default=True)


class IncomeIn(BaseModel):
    amount: float = Field(gt=0, le=999999)
    source: str = Field(default="Other", max_length=64)
    income_date: Optional[str] = None


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    target_amount: float = Field(gt=0, le=9999999)
    current_amount: float = Field(ge=0, le=9999999, default=0)
    deadline: Optional[str] = None


class GoalUpdateIn(BaseModel):
    name: Optional[str] = Field(None, max_length=256)
    target_amount: Optional[float] = Field(None, gt=0, le=9999999)
    current_amount: Optional[float] = Field(None, ge=0, le=9999999)
    deadline: Optional[str] = None


@router.get("/expenses")
@limiter.limit("120/minute")
async def api_list_expenses(request: Request):
    sid = _session_id(request)
    touch_activity()
    return {"expenses": list_expenses(sid)}


@router.post("/expenses")
@limiter.limit("60/minute")
async def api_create_expense(request: Request, body: ExpenseIn):
    sid = _session_id(request)
    touch_activity()
    if count_expenses(sid) >= DEMO_MAX_EXPENSES_PER_SESSION:
        raise HTTPException(status_code=403, detail="Demo capacity reached")
    d = _validate_date(body.expense_date)
    eid = add_expense(
        sid,
        body.amount,
        body.description.strip(),
        body.category.strip() or "Other",
        d[:10],
    )
    return {"id": eid, "ok": True}


@router.post("/expenses/{expense_id}")
@limiter.limit("60/minute")
async def api_update_expense(
    request: Request, expense_id: int, body: ExpenseIn
):
    sid = _session_id(request)
    touch_activity()
    d = _validate_date(body.expense_date)
    ok = update_expense(
        sid,
        expense_id,
        body.amount,
        body.description.strip(),
        body.category.strip() or "Other",
        d[:10],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"id": expense_id, "ok": True}


@router.post("/budgets")
@limiter.limit("30/minute")
async def api_create_budget(request: Request, body: BudgetIn):
    sid = _session_id(request)
    touch_activity()
    month = _validate_month(body.month)
    if count_budgets(sid) >= DEMO_MAX_BUDGETS_PER_SESSION:
        raise HTTPException(status_code=403, detail="Demo capacity reached")
    bid = add_budget(sid, month, body.category.strip() or "Other", body.limit)
    return {"id": bid, "ok": True}


@router.post("/budgets/{budget_id}")
@limiter.limit("30/minute")
async def api_update_budget(request: Request, budget_id: int, body: BudgetIn):
    sid = _session_id(request)
    touch_activity()
    month = _validate_month(body.month)
    try:
        ok = update_budget(
            sid,
            budget_id,
            month,
            body.category.strip() or "Other",
            body.limit,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid budget update")
    if not ok:
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"id": budget_id, "ok": True}


@router.get("/income")
@limiter.limit("120/minute")
async def api_list_income(request: Request):
    sid = _session_id(request)
    touch_activity()
    return {"income": list_income(sid)}


@router.post("/income")
@limiter.limit("60/minute")
async def api_create_income(request: Request, body: IncomeIn):
    sid = _session_id(request)
    touch_activity()
    if count_income(sid) >= DEMO_MAX_INCOME_PER_SESSION:
        raise HTTPException(status_code=403, detail="Demo capacity reached")
    d = _validate_date(body.income_date)
    iid = add_income(sid, body.amount, body.source.strip() or "Other", d)
    return {"id": iid, "ok": True}


@router.patch("/income/{income_id}")
@limiter.limit("60/minute")
async def api_update_income(request: Request, income_id: int, body: IncomeIn):
    sid = _session_id(request)
    touch_activity()
    d = _validate_date(body.income_date)
    ok = update_income(
        sid, income_id, body.amount, body.source.strip() or "Other", d
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Income not found")
    return {"id": income_id, "ok": True}


@router.get("/goals")
@limiter.limit("120/minute")
async def api_list_goals(request: Request):
    sid = _session_id(request)
    touch_activity()
    return {"goals": list_goals(sid)}


@router.post("/goals")
@limiter.limit("30/minute")
async def api_create_goal(request: Request, body: GoalIn):
    sid = _session_id(request)
    touch_activity()
    if count_goals(sid) >= DEMO_MAX_GOALS_PER_SESSION:
        raise HTTPException(status_code=403, detail="Demo capacity reached")
    deadline = body.deadline[:10] if body.deadline else None
    gid = add_goal(
        sid,
        body.name.strip(),
        body.target_amount,
        body.current_amount,
        deadline,
    )
    return {"id": gid, "ok": True}


@router.get("/goals/{goal_id}")
@limiter.limit("120/minute")
async def api_get_goal(request: Request, goal_id: int):
    sid = _session_id(request)
    touch_activity()
    goal = get_goal(sid, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.patch("/goals/{goal_id}")
@limiter.limit("30/minute")
async def api_update_goal(request: Request, goal_id: int, body: GoalUpdateIn):
    sid = _session_id(request)
    touch_activity()
    kwargs = {}
    if body.name is not None:
        kwargs["name"] = body.name.strip() or "Goal"
    if body.target_amount is not None:
        kwargs["target_amount"] = body.target_amount
    if body.current_amount is not None:
        kwargs["current_amount"] = body.current_amount
    if body.deadline is not None:
        kwargs["deadline"] = body.deadline[:10] if body.deadline else None
    if not kwargs:
        return {"id": goal_id, "ok": True}
    ok = update_goal(sid, goal_id, **kwargs)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"id": goal_id, "ok": True}


@router.post("/insights/anomalies/{expense_id}/feedback")
@limiter.limit("30/minute")
async def api_anomaly_feedback(
    request: Request, expense_id: int, body: InsightsFeedbackIn
):
    sid = _session_id(request)
    touch_activity()

    # Ownership check: feedback must correspond to an expense in this session.
    exp = get_expense(sid, expense_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")

    set_insights_feedback(sid, expense_id, body.decision)
    return {"id": expense_id, "ok": True}


@router.post("/recommendations/run")
@limiter.limit("10/minute")
async def api_run_recommendations(request: Request, body: RecommendationsRunIn):
    sid = _session_id(request)
    touch_activity()

    m = body.month.strip() if body.month else date.today().isoformat()[:7]
    m = _validate_month(m)

    risk = (body.risk_tolerance or "balanced").strip().lower()
    if risk not in ("conservative", "balanced", "aggressive"):
        risk = "balanced"

    budgets = list_budgets(sid, m)
    budgets_by_cat = {b["category"]: float(b["limit"]) for b in budgets}

    cat_spend = category_spend_for_month(sid, m)  # [{category,total}]
    spend_by_cat = {x["category"]: float(x["total"]) for x in cat_spend}
    total_spend = float(total_spend_for_month(sid, m))

    total_budgeted = sum(budgets_by_cat.values()) if budgets_by_cat else 0.0
    total_remaining = 0.0
    for cat, limit in budgets_by_cat.items():
        spent = spend_by_cat.get(cat, 0.0)
        total_remaining += max(limit - spent, 0.0)

    recs = []

    # ---- Budget-driven recommendations ----
    if budgets_by_cat:
        for cat, limit in sorted(budgets_by_cat.items(), key=lambda kv: kv[1], reverse=True):
            spent = spend_by_cat.get(cat, 0.0)
            if limit <= 0:
                continue
            usage = spent / limit
            if usage >= 1.0:
                overspent = spent - limit
                recs.append(
                    {
                        "type": "budget",
                        "title": f"Reduce {cat} spending for {m}",
                        "why": f"You overspent by ${overspent:.2f} vs your ${limit:.2f} budget. Spend in this category is ${spent:.2f}.",
                        "score": 0.85 if risk == "balanced" else 0.8,
                    }
                )
            elif usage >= 0.8:
                recs.append(
                    {
                        "type": "budget",
                        "title": f"Stay under your {cat} budget in {m}",
                        "why": f"You're at {usage*100:.0f}% of your ${limit:.2f} {cat} limit (spent ${spent:.2f}). Consider a tighter plan for the rest of the month.",
                        "score": 0.65,
                    }
                )
    else:
        # No budgets: recommend setting budgets for your top categories.
        top = sorted(cat_spend, key=lambda x: float(x["total"]), reverse=True)[:3]
        for x in top:
            cat = x["category"]
            amt = float(x["total"])
            recs.append(
                {
                    "type": "budget",
                    "title": f"Create a {cat} budget for {m}",
                    "why": f"Your {cat} spend is ${amt:.2f} in {m}. Budgeting the top categories usually improves predictability.",
                    "score": 0.6,
                }
            )

    # ---- Savings / allocation-style recommendation (dummy, deterministic) ----
    if body.use_budget and budgets_by_cat:
        if total_remaining > 0:
            base = 0.4 if risk == "conservative" else (0.55 if risk == "balanced" else 0.7)
            alloc = total_remaining * base
            recs.append(
                {
                    "type": "allocation",
                    "title": "Allocate remaining budget to your savings plan",
                    "why": f"You have about ${total_remaining:.2f} remaining across your budgets in {m}. With a {risk} profile, consider allocating roughly ${alloc:.2f} toward long-term savings.",
                    "score": 0.62,
                }
            )
        else:
            recs.append(
                {
                    "type": "allocation",
                    "title": "First stabilize cashflow, then optimize allocation",
                    "why": f"Your budgets are fully utilized in {m} (total spend: ${total_spend:.2f}). Before changing allocations, reduce variable spending to rebuild remaining budget.",
                    "score": 0.7,
                }
            )

    # Ensure stable ordering + max items
    recs = sorted(recs, key=lambda r: float(r.get("score", 0.0)), reverse=True)[:6]

    portfolio_summary = (
        f"Demo analysis for {m}. Total spend ${total_spend:.2f}. "
        f"{'Budgets are active' if budgets_by_cat else 'No budgets yet'}."
    )

    return {"month": m, "portfolio_summary": portfolio_summary, "recommendations": recs}
