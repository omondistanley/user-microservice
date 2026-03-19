"""HTML pages: landing, watch, interactive shell."""
import json
import os
import re
from typing import Optional
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth_demo import COOKIE_NAME, verify_demo_token
from app.config import DEMO_AI_ENABLED, PUBLIC_BASE_URL
from app.db import (
    get_budget,
    get_expense,
    get_goal,
    expense_month_totals,
    WATCH_BUDGETS_BY_KEY,
    WATCH_DEFAULT_MONTH,
    WATCH_EXPENSES_BY_KEY,
    WATCH_SESSION_ID,
    _normalize_category,
    list_budgets,
    list_expenses,
    list_expenses_for_month,
    list_goals,
    list_income,
    category_spend_for_month,
    spend_for_category_month,
    total_spend_for_month,
    touch_activity,
)

_templates_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
_SCENES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "static", "demo", "scenes.json")


def _load_scenes():
    with open(_SCENES_PATH, encoding="utf-8") as f:
        return json.load(f)


templates = Jinja2Templates(directory=os.path.abspath(_templates_dir))

router = APIRouter(tags=["pages"])

# Fixture numbers for demo UI (no API calls)
FIXTURE = {
    "net_worth": "24,350",
    "month_spend": "1,275",
    "food_spend": "640",
    "budget_food_limit": "500",
    "budget_food_spent": "480",
}

# Fixture data for pages that don't persist (recurring, notifications, household, etc.)
FIXTURE_RECURRING = [
    {"description": "Netflix", "amount": 12.99, "category": "Entertainment", "frequency": "Monthly"},
    {"description": "Rent", "amount": 1200.0, "category": "Housing", "frequency": "Monthly"},
]
FIXTURE_NOTIFICATIONS = [
    {"id": 1, "title": "Budget alert", "body": "Food budget at 90% for this month.", "read": False, "created": "2026-03-15"},
]
FIXTURE_HOUSEHOLD = {"name": "Personal", "members": 1}
FIXTURE_SESSIONS = [{"device": "Current session", "last_active": "Now"}]
FIXTURE_PROFILE = {"name": "Demo User", "email": "demo@pocketii.example"}
FIXTURE_SAVED_VIEWS = [
    {"name": "March 2026 spending", "created": "2026-03-01"},
]

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _ctx(request: Request, **extra):
    return {
        "request": request,
        "fixture": FIXTURE,
        "public_base": PUBLIC_BASE_URL,
        "demo_ai_enabled": DEMO_AI_ENABLED,
        **extra,
    }


@router.get("/health")
async def health():
    return {"status": "ok", "service": "pocketii-demo"}


@router.get("/robots.txt")
async def robots():
    return HTMLResponse("User-agent: *\nDisallow: /\n", media_type="text/plain")


@router.get("/demo", response_class=HTMLResponse)
async def demo_landing(request: Request):
    return templates.TemplateResponse("demo_landing.html", _ctx(request))


@router.get("/demo/watch", response_class=HTMLResponse)
async def demo_watch(request: Request):
    return RedirectResponse(url="/demo/watch/app/dashboard", status_code=302)


def _watch_month(month: Optional[str]) -> str:
    m = (month or WATCH_DEFAULT_MONTH).strip()
    if not _MONTH_RE.match(m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    return m


@router.get("/demo/watch/app/dashboard", response_class=HTMLResponse)
async def watch_dashboard(request: Request, month: Optional[str] = None):
    touch_activity()
    m = _watch_month(month)
    return templates.TemplateResponse(
        "demo_watch_dashboard.html",
        _ctx(request, scenes=_load_scenes(), month=m),
    )


@router.get("/demo/watch/app/expenses", response_class=HTMLResponse)
async def watch_expenses(request: Request, month: Optional[str] = None):
    touch_activity()
    m = _watch_month(month)
    expenses = list_expenses_for_month(WATCH_SESSION_ID, m)

    # Build key mapping (so the tour can link to stable detail routes).
    fingerprint_to_key = {}
    for key, e in WATCH_EXPENSES_BY_KEY.items():
        fp = (
            str(e["expense_date"])[:10]
            + "|"
            + str(e["description"])
            + "|"
            + _normalize_category(e["category"])
            + "|"
            + str(float(e["amount"]))
        )
        fingerprint_to_key[fp] = key

    for e in expenses:
        fp = (
            str(e.get("expense_date", ""))[:10]
            + "|"
            + str(e.get("description", ""))
            + "|"
            + str(e.get("category", "Other"))
            + "|"
            + str(float(e.get("amount", 0.0)))
        )
        e["detail_key"] = fingerprint_to_key.get(fp)

    return templates.TemplateResponse(
        "demo_watch_expenses.html",
        _ctx(request, scenes=_load_scenes(), month=m, expenses=expenses),
    )


@router.get("/demo/watch/app/expenses/detail/{detail_key}", response_class=HTMLResponse)
async def watch_expense_detail(request: Request, detail_key: str):
    touch_activity()
    e = WATCH_EXPENSES_BY_KEY.get(detail_key)
    if not e:
        raise HTTPException(status_code=404, detail="Expense not found")
    return templates.TemplateResponse(
        "demo_watch_expense_detail.html",
        _ctx(
            request,
            scenes=_load_scenes(),
            expense={
                "amount": e["amount"],
                "description": e["description"],
                "category": e["category"],
                "expense_date": e["expense_date"],
            },
        ),
    )


@router.get("/demo/watch/app/budgets", response_class=HTMLResponse)
async def watch_budgets(request: Request, month: Optional[str] = None):
    touch_activity()
    m = _watch_month(month)
    budgets = list_budgets(WATCH_SESSION_ID, m)

    month_cat_to_key = {}
    for key, b in WATCH_BUDGETS_BY_KEY.items():
        month_cat_to_key[(b["month"], _normalize_category(b["category"]))] = key

    for b in budgets:
        spent = spend_for_category_month(WATCH_SESSION_ID, b["category"], m)
        b["spent"] = spent
        b["remaining"] = max(float(b["limit"]) - spent, 0.0)
        b["pct"] = min(100.0, (spent / float(b["limit"])) * 100.0) if b["limit"] else 0.0
        b["detail_key"] = month_cat_to_key.get((m, _normalize_category(b["category"])))

    total_spend = total_spend_for_month(WATCH_SESSION_ID, m)
    return templates.TemplateResponse(
        "demo_watch_budgets.html",
        _ctx(request, scenes=_load_scenes(), month=m, budgets=budgets, total_spend=total_spend),
    )


@router.get("/demo/watch/app/budgets/detail/{detail_key}", response_class=HTMLResponse)
async def watch_budget_detail(request: Request, detail_key: str):
    touch_activity()
    b = WATCH_BUDGETS_BY_KEY.get(detail_key)
    if not b:
        raise HTTPException(status_code=404, detail="Budget not found")
    return templates.TemplateResponse(
        "demo_watch_budget_detail.html",
        _ctx(request, scenes=_load_scenes(), budget=b),
    )


@router.get("/demo/watch/app/insights", response_class=HTMLResponse)
async def watch_insights(request: Request, month: Optional[str] = None):
    touch_activity()
    m = _watch_month(month)

    selected_y = int(m[:4])
    selected_mo = int(m[5:7])

    def _month_index(y: int, mo: int) -> int:
        return y * 12 + (mo - 1)

    def _add_month(y: int, mo: int, delta: int) -> tuple[int, int]:
        idx = _month_index(y, mo) + delta
        return idx // 12, (idx % 12) + 1

    # ---- Spend forecast (next 3 months) ----
    hist = expense_month_totals(WATCH_SESSION_ID)
    selected_idx = _month_index(selected_y, selected_mo)
    hist_points = []
    for h in hist:
        hm = h.get("month", "")
        if not _MONTH_RE.match(hm):
            continue
        hy = int(hm[:4])
        hmo = int(hm[5:7])
        hist_points.append((_month_index(hy, hmo), float(h.get("total", 0.0))))
    hist_points = sorted(hist_points, key=lambda x: x[0])
    eligible = [p for p in hist_points if p[0] <= selected_idx]
    eligible = eligible[-6:] if eligible else []
    avg_total = sum(t for _, t in eligible) / len(eligible) if eligible else 0.0

    last_total = eligible[-1][1] if eligible else 0.0
    if avg_total > 0:
        multiplier = 1.0 + 0.15 * (last_total - avg_total) / max(avg_total, 1e-9)
    else:
        multiplier = 1.0

    forecast = []
    for i in range(1, 4):
        ny, nmo = _add_month(selected_y, selected_mo, i)
        nm = f"{ny:04d}-{nmo:02d}"
        projected = avg_total * multiplier
        forecast.append({"month": nm, "projected_amount": round(projected, 2)})

    # ---- Anomalies ----
    expenses = list_expenses_for_month(WATCH_SESSION_ID, m)
    anomalies = []
    if expenses:
        amounts = [float(e["amount"]) for e in expenses if e.get("amount") is not None]
        if amounts:
            mean = sum(amounts) / len(amounts)
            var = sum((a - mean) ** 2 for a in amounts) / len(amounts)
            std = var ** 0.5
            threshold = mean + 2.0 * std if std > 0 else mean * 1.5

            candidates = [e for e in expenses if float(e["amount"]) >= threshold]
            if not candidates and len(expenses) >= 3:
                candidates = sorted(expenses, key=lambda e: float(e["amount"]), reverse=True)[:3]

            for e in sorted(candidates, key=lambda x: float(x["amount"]), reverse=True)[:10]:
                amt = float(e["amount"])
                anomalies.append(
                    {
                        "expense_id": int(e["id"]),
                        "date": e["expense_date"],
                        "amount": amt,
                        "reason": "high_amount",
                        "detail": f"Amount ${amt:.2f} is above your typical ${mean:.2f} spend in {m}.",
                    }
                )

    return templates.TemplateResponse(
        "demo_watch_insights.html",
        _ctx(request, scenes=_load_scenes(), month=m, forecast=forecast, anomalies=anomalies),
    )


@router.get("/demo/watch/app/recommendations", response_class=HTMLResponse)
async def watch_recommendations(request: Request, month: Optional[str] = None):
    touch_activity()
    m = _watch_month(month)

    # Match the deterministic API logic (risk=balanced, use_budget=true).
    budgets = list_budgets(WATCH_SESSION_ID, m)
    budgets_by_cat = {b["category"]: float(b["limit"]) for b in budgets}
    cat_spend = category_spend_for_month(WATCH_SESSION_ID, m)
    spend_by_cat = {x["category"]: float(x["total"]) for x in cat_spend}
    total_spend = float(total_spend_for_month(WATCH_SESSION_ID, m))

    total_remaining = 0.0
    for cat, limit in budgets_by_cat.items():
        spent = spend_by_cat.get(cat, 0.0)
        total_remaining += max(limit - spent, 0.0)

    recs = []
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
                        "score": 0.85,
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

    if budgets_by_cat:
        if total_remaining > 0:
            alloc = total_remaining * 0.4
            recs.append(
                {
                    "type": "allocation",
                    "title": "Allocate remaining budget to your savings plan",
                    "why": f"You have about ${total_remaining:.2f} remaining across your budgets in {m}. With a balanced profile, consider allocating roughly ${alloc:.2f} toward long-term savings.",
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

    recs = sorted(recs, key=lambda r: float(r.get("score", 0.0)), reverse=True)[:6]
    portfolio_summary = (
        f"Demo analysis for {m}. Total spend ${total_spend:.2f}. "
        f"{'Budgets are active' if budgets_by_cat else 'No budgets yet'}."
    )

    return templates.TemplateResponse(
        "demo_watch_recommendations.html",
        _ctx(request, scenes=_load_scenes(), month=m, recommendations=recs, portfolio_summary=portfolio_summary),
    )


@router.get("/demo/watch/app/investments", response_class=HTMLResponse)
async def watch_investments(request: Request):
    touch_activity()
    return templates.TemplateResponse(
        "demo_watch_investments.html",
        _ctx(request, scenes=_load_scenes()),
    )


@router.get("/demo/start", response_class=HTMLResponse)
async def demo_start(request: Request, next: Optional[str] = None):
    nxt = next if next and next.startswith("/demo/") else "/demo/app/dashboard"
    return templates.TemplateResponse("demo_start.html", _ctx(request, next_path=nxt))


def _require_demo(request: Request) -> Optional[RedirectResponse]:
    if verify_demo_token(request.cookies.get(COOKIE_NAME)):
        return None
    return RedirectResponse(url="/demo/start?next=" + request.url.path, status_code=302)


def _sid(request: Request):
    token = verify_demo_token(request.cookies.get(COOKIE_NAME))
    return str(token["sid"]) if token else None


@router.get("/demo/app/dashboard", response_class=HTMLResponse)
async def app_dashboard(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    sid = _sid(request)
    m = date.today().isoformat()[:7]
    expenses = list_expenses(sid)[:15] if sid else []
    budgets = list_budgets(sid, m) if sid else []
    for b in budgets:
        b["spent"] = spend_for_category_month(sid, b["category"], m)
        b["remaining"] = max(float(b["limit"]) - b["spent"], 0.0)
        b["pct"] = min(100.0, (b["spent"] / float(b["limit"])) * 100.0) if b["limit"] else 0.0
    goals = list_goals(sid)[:5] if sid else []
    income_list = list_income(sid) if sid else []
    total_spend = total_spend_for_month(sid, m) if sid else 0.0
    category_spend = category_spend_for_month(sid, m) if sid else []
    total_income_month = sum(float(i["amount"]) for i in income_list if (i.get("income_date") or "")[:7] == m)
    return templates.TemplateResponse(
        "demo_app_dashboard.html",
        _ctx(
            request,
            month=m,
            expenses=expenses,
            budgets=budgets,
            goals=goals,
            income_list=income_list,
            total_spend=total_spend,
            total_income_month=total_income_month,
            category_spend=category_spend,
        ),
    )


@router.get("/demo/app/expenses", response_class=HTMLResponse)
async def app_expenses(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    sid = verify_demo_token(request.cookies.get(COOKIE_NAME))["sid"]
    expenses = list_expenses(sid)
    return templates.TemplateResponse(
        "demo_app_expenses.html", _ctx(request, expenses=expenses)
    )


@router.get("/demo/app/expenses/add", response_class=HTMLResponse)
async def app_expenses_add(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    m = date.today().isoformat()[:7]
    return templates.TemplateResponse(
        "demo_app_expenses_add.html", _ctx(request, month=m)
    )


@router.get("/demo/app/expenses/{expense_id}", response_class=HTMLResponse)
async def app_expense_detail(request: Request, expense_id: str):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    token = verify_demo_token(request.cookies.get(COOKIE_NAME))
    if not token:
        raise HTTPException(status_code=401, detail="Demo session required")
    sid = str(token["sid"])
    try:
        eid = int(expense_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expense id")

    expense = get_expense(sid, eid)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return templates.TemplateResponse(
        "demo_app_expense_detail.html", _ctx(request, expense=expense)
    )


@router.get("/demo/app/budgets", response_class=HTMLResponse)
async def app_budgets(request: Request, month: Optional[str] = None):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    token = verify_demo_token(request.cookies.get(COOKIE_NAME))
    sid = str(token["sid"])

    m = month.strip() if month else date.today().isoformat()[:7]
    if not _MONTH_RE.match(m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    budgets = list_budgets(sid, m)
    for b in budgets:
        spent = spend_for_category_month(sid, b["category"], m)
        b["spent"] = spent
        b["remaining"] = max(float(b["limit"]) - spent, 0.0)
        if b["limit"]:
            b["pct"] = min(100.0, (spent / float(b["limit"])) * 100.0)
        else:
            b["pct"] = 0.0

    total_spend = total_spend_for_month(sid, m)
    return templates.TemplateResponse(
        "demo_app_budgets.html",
        _ctx(request, budgets=budgets, month=m, total_spend=total_spend),
    )


@router.get("/demo/app/budgets/add", response_class=HTMLResponse)
async def app_budget_add(request: Request, month: Optional[str] = None):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    m = month.strip() if month else date.today().isoformat()[:7]
    if not _MONTH_RE.match(m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    return templates.TemplateResponse(
        "demo_app_budgets_add.html", _ctx(request, month=m)
    )


@router.get("/demo/app/budgets/{budget_id}", response_class=HTMLResponse)
async def app_budget_detail(request: Request, budget_id: str):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()

    token = verify_demo_token(request.cookies.get(COOKIE_NAME))
    sid = str(token["sid"])

    try:
        bid = int(budget_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid budget id")

    budget = get_budget(sid, bid)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return templates.TemplateResponse(
        "demo_app_budget_detail.html",
        _ctx(request, budget=budget),
    )


@router.get("/demo/app/insights", response_class=HTMLResponse)
async def app_insights(request: Request, month: Optional[str] = None):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()

    token = verify_demo_token(request.cookies.get(COOKIE_NAME))
    sid = str(token["sid"])

    m = month.strip() if month else date.today().isoformat()[:7]
    if not _MONTH_RE.match(m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    # ---- Spend forecast (next 3 months) ----
    selected_y = int(m[:4])
    selected_mo = int(m[5:7])

    def _month_index(y: int, mo: int) -> int:
        return y * 12 + (mo - 1)

    def _add_month(y: int, mo: int, delta: int) -> tuple[int, int]:
        idx = _month_index(y, mo) + delta
        return idx // 12, (idx % 12) + 1

    hist = expense_month_totals(sid)
    selected_idx = _month_index(selected_y, selected_mo)
    hist_points = []
    for h in hist:
        hm = h.get("month", "")
        if not _MONTH_RE.match(hm):
            continue
        hy = int(hm[:4])
        hmo = int(hm[5:7])
        hist_points.append((_month_index(hy, hmo), float(h.get("total", 0.0))))
    hist_points = sorted(hist_points, key=lambda x: x[0])
    eligible = [p for p in hist_points if p[0] <= selected_idx]
    eligible = eligible[-6:] if eligible else []
    avg_total = sum(t for _, t in eligible) / len(eligible) if eligible else 0.0

    # small deterministic adjustment based on most recent month in eligible set
    last_total = eligible[-1][1] if eligible else 0.0
    if avg_total > 0:
        multiplier = 1.0 + 0.15 * (last_total - avg_total) / max(avg_total, 1e-9)
    else:
        multiplier = 1.0

    forecast = []
    for i in range(1, 4):
        ny, nmo = _add_month(selected_y, selected_mo, i)
        nm = f"{ny:04d}-{nmo:02d}"
        projected = avg_total * multiplier
        forecast.append({"month": nm, "projected_amount": round(projected, 2)})

    # ---- Anomalies (unusual expenses) ----
    expenses = list_expenses_for_month(sid, m)
    anomalies = []
    if expenses:
        amounts = [float(e["amount"]) for e in expenses if e.get("amount") is not None]
        if amounts:
            mean = sum(amounts) / len(amounts)
            var = sum((a - mean) ** 2 for a in amounts) / len(amounts)
            std = var ** 0.5
            threshold = mean + 2.0 * std if std > 0 else mean * 1.5

            candidates = [e for e in expenses if float(e["amount"]) >= threshold]
            if not candidates and len(expenses) >= 3:
                candidates = sorted(expenses, key=lambda e: float(e["amount"]), reverse=True)[:3]

            for e in sorted(
                candidates, key=lambda x: float(x["amount"]), reverse=True
            )[:10]:
                amt = float(e["amount"])
                anomalies.append(
                    {
                        "expense_id": int(e["id"]),
                        "date": e["expense_date"],
                        "amount": amt,
                        "reason": "high_amount",
                        "detail": f"Amount ${amt:.2f} is above your typical ${mean:.2f} spend in {m}.",
                    }
                )

    return templates.TemplateResponse(
        "demo_app_insights.html",
        _ctx(request, month=m, forecast=forecast, anomalies=anomalies),
    )


@router.get("/demo/app/recommendations", response_class=HTMLResponse)
async def app_recommendations(request: Request, month: Optional[str] = None):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()

    m = month.strip() if month else date.today().isoformat()[:7]
    if not _MONTH_RE.match(m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    return templates.TemplateResponse(
        "demo_app_recommendations.html", _ctx(request, month=m)
    )


@router.get("/demo/app/integrations", response_class=HTMLResponse)
async def app_integrations_redirect(request: Request):
    return RedirectResponse(url="/demo/app/settings/integrations", status_code=302)


@router.get("/demo/app/settings/integrations", response_class=HTMLResponse)
async def app_settings_integrations(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse("demo_app_integrations.html", _ctx(request))


@router.get("/demo/app/investments", response_class=HTMLResponse)
async def app_investments(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse("demo_app_investments.html", _ctx(request))


@router.get("/demo/app/net-worth", response_class=HTMLResponse)
async def app_net_worth(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse("demo_app_net_worth.html", _ctx(request))


@router.get("/demo/app/income", response_class=HTMLResponse)
async def app_income_list(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    sid = _sid(request)
    income_list = list_income(sid) if sid else []
    m = date.today().isoformat()[:7]
    total_income = sum(float(i.get("amount", 0)) for i in income_list)
    income_this_month = sum(
        float(i.get("amount", 0))
        for i in income_list
        if (i.get("income_date") or "")[:7] == m
    )
    return templates.TemplateResponse(
        "demo_app_income_list.html",
        _ctx(
            request,
            income_list=income_list,
            total_income=total_income,
            income_this_month=income_this_month,
        ),
    )


@router.get("/demo/app/income/add", response_class=HTMLResponse)
async def app_income_add(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse("demo_app_income_add.html", _ctx(request))


@router.get("/demo/app/recurring", response_class=HTMLResponse)
async def app_recurring(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse(
        "demo_app_recurring.html",
        _ctx(request, recurring=FIXTURE_RECURRING),
    )


@router.get("/demo/app/goals", response_class=HTMLResponse)
async def app_goals_list(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    sid = _sid(request)
    goals = list_goals(sid) if sid else []
    return templates.TemplateResponse(
        "demo_app_goals.html", _ctx(request, goals=goals)
    )


@router.get("/demo/app/goals/add", response_class=HTMLResponse)
async def app_goals_add(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse("demo_app_goals_add.html", _ctx(request))


@router.get("/demo/app/goals/{goal_id}", response_class=HTMLResponse)
async def app_goal_detail(request: Request, goal_id: str):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    sid = _sid(request)
    try:
        gid = int(goal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid goal id")
    goal = get_goal(sid, gid) if sid else None
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return templates.TemplateResponse(
        "demo_app_goal_detail.html", _ctx(request, goal=goal)
    )


@router.get("/demo/app/reports", response_class=HTMLResponse)
async def app_reports(request: Request, month: Optional[str] = None):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    sid = _sid(request)
    m = (month or date.today().isoformat()[:7]).strip()
    if not _MONTH_RE.match(m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    category_spend = category_spend_for_month(sid, m) if sid else []
    total_spend = total_spend_for_month(sid, m) if sid else 0.0
    return templates.TemplateResponse(
        "demo_app_reports.html",
        _ctx(request, month=m, category_spend=category_spend, total_spend=total_spend),
    )


@router.get("/demo/app/reports/category/{category_code}", response_class=HTMLResponse)
async def app_reports_category(request: Request, category_code: str):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse(
        "demo_app_reports_category.html",
        _ctx(request, category_code=category_code or "Other"),
    )


@router.get("/demo/app/notifications", response_class=HTMLResponse)
async def app_notifications(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse(
        "demo_app_notifications.html",
        _ctx(request, notifications=FIXTURE_NOTIFICATIONS),
    )


@router.get("/demo/app/household", response_class=HTMLResponse)
async def app_household(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse(
        "demo_app_household.html",
        _ctx(request, household=FIXTURE_HOUSEHOLD),
    )


@router.get("/demo/app/sessions", response_class=HTMLResponse)
async def app_sessions(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse(
        "demo_app_sessions.html",
        _ctx(request, sessions=FIXTURE_SESSIONS),
    )


@router.get("/demo/app/profile", response_class=HTMLResponse)
async def app_profile(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse(
        "demo_app_profile.html",
        _ctx(request, profile=FIXTURE_PROFILE),
    )


@router.get("/demo/app/settings", response_class=HTMLResponse)
async def app_settings(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse("demo_app_settings.html", _ctx(request))


@router.get("/demo/app/saved-views", response_class=HTMLResponse)
async def app_saved_views(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse(
        "demo_app_saved_views.html",
        _ctx(request, saved_views=FIXTURE_SAVED_VIEWS),
    )


@router.get("/demo/app/link-bank", response_class=HTMLResponse)
async def app_link_bank(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse("demo_app_link_bank.html", _ctx(request))


@router.get("/demo/app/link-bank/success", response_class=HTMLResponse)
async def app_link_bank_success(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse("demo_app_link_bank_success.html", _ctx(request))


@router.get("/demo/app/link-bank/select", response_class=HTMLResponse)
async def app_link_bank_select(request: Request):
    redir = _require_demo(request)
    if redir:
        return redir
    touch_activity()
    return templates.TemplateResponse("demo_app_link_bank_select.html", _ctx(request))


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse(url="/demo", status_code=302)
