import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import psycopg2
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers import users, oauth, notifications, settings, households, saved_views, sessions, integrations, net_worth
from app.services.email_verification_service import verify_email_token
from app.core.config import (
    get_cors_origins,
    EXPENSE_SERVICE_URL,
    BUDGET_SERVICE_URL,
    INVESTMENT_SERVICE_URL,
    EXPENSE_API_BASE_FRONTEND,
    BUDGET_API_BASE_FRONTEND,
    GATEWAY_PUBLIC_URL,
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
    SECURITY_HEADERS_ENABLED,
    HSTS_MAX_AGE_SECONDS,
    CSP_POLICY,
    RATE_LIMIT_API_PER_MINUTE,
    RATE_LIMIT_EXPENSIVE_PER_USER_PER_MINUTE,
)
from app.core.dependencies import get_current_user as get_current_user_dep
from app.proxy import proxy_request
from app.core.rate_limit import evaluate_rate_limit, get_client_ip
from app.core.security import decode_token

app = FastAPI()
PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
logger = logging.getLogger("user_microservice")
EXPENSIVE_RATE_LIMIT_PATH_PREFIXES = (
    "/api/v1/expenses/summary",
    "/api/v1/expenses/export",
    "/api/v1/expenses/balance",
    "/api/v1/income/summary",
    "/api/v1/cashflow/summary",
    "/api/v1/recurring-expenses",
    "/api/v1/budgets/alerts/evaluate",
    "/user/me/export",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
)


@app.middleware("http")
async def redirect_to_gateway_if_configured(request: Request, call_next):
    """When GATEWAY_PUBLIC_URL is set, redirect direct hits to user service (port 8000) to the gateway so auth and API bases are consistent."""
    if GATEWAY_PUBLIC_URL:
        host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").strip().lower()
        if request.method == "GET" and host in ("localhost:8000", "127.0.0.1:8000"):
            base = GATEWAY_PUBLIC_URL.rstrip("/")
            path = request.url.path or "/"
            if not path.startswith("/"):
                path = "/" + path
            query = request.url.query
            redirect_url = f"{base}{path}" + (f"?{query}" if query else "")
            return RedirectResponse(redirect_url, status_code=307)
    return await call_next(request)


# Frontend: expense_tracker/frontend (sibling of user-microservice)
# __file__ = .../user-microservice/app/main.py -> parent.parent = user-microservice -> parent.parent.parent = expense_tracker
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
_TEMPLATES_DIR = _FRONTEND_DIR / "templates"
_STATIC_DIR = _FRONTEND_DIR / "static"

if _TEMPLATES_DIR.exists():
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
else:
    templates = None

app.include_router(users.router)
app.include_router(oauth.router)
app.include_router(notifications.router)
app.include_router(settings.router)
app.include_router(households.router)
app.include_router(saved_views.router)
app.include_router(sessions.router)
app.include_router(integrations.router)
app.include_router(net_worth.router)

# Proxy /api/v1/* to backends only when gateway is not used (frontend then uses same-origin and we proxy)
if EXPENSE_SERVICE_URL and not GATEWAY_PUBLIC_URL:
    @app.api_route("/api/v1/expenses", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_expenses_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/expenses", "")

    @app.api_route("/api/v1/expenses/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_expenses_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/expenses", path)

    @app.api_route("/api/v1/income", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_income_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/income", "")

    @app.api_route("/api/v1/income/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_income_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/income", path)

    @app.api_route("/api/v1/cashflow", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_cashflow_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/cashflow", "")

    @app.api_route("/api/v1/cashflow/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_cashflow_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/cashflow", path)

    @app.api_route("/api/v1/recurring-expenses", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_recurring_expenses_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/recurring-expenses", "")

    @app.api_route("/api/v1/recurring-expenses/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_recurring_expenses_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/recurring-expenses", path)

    @app.api_route("/api/v1/categories", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_categories_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/categories", "")

    @app.api_route("/api/v1/categories/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_categories_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/categories", path)

    @app.api_route("/api/v1/tags", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_tags_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/tags", "")

    @app.api_route("/api/v1/tags/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_tags_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/tags", path)

    @app.api_route("/api/v1/receipts", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_receipts_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/receipts", "")

    @app.api_route("/api/v1/receipts/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_receipts_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/receipts", path)

    @app.api_route("/api/v1/plaid", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_plaid_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/plaid", "")

    @app.api_route("/api/v1/plaid/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_plaid_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/plaid", path)

    @app.api_route("/api/v1/teller", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_teller_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/teller", "")

    @app.api_route("/api/v1/teller/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_teller_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/teller", path)

    @app.api_route("/api/v1/truelayer", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_truelayer_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/truelayer", "")

    @app.api_route("/api/v1/truelayer/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_truelayer_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/truelayer", path)

    @app.api_route("/api/v1/bank", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_bank_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/bank", "")

    @app.api_route("/api/v1/bank/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_bank_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/bank", path)

    @app.api_route("/api/v1/goals", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_goals_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/goals", "")

    @app.api_route("/api/v1/goals/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_goals_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/goals", path)

    @app.api_route("/api/v1/insights", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_insights_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/insights", "")

    @app.api_route("/api/v1/insights/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_insights_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/insights", path)

    @app.api_route("/api/v1/reminders", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_reminders_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/reminders", "")

    @app.api_route("/api/v1/reminders/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_reminders_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/reminders", path)

    @app.api_route("/api/v1/export", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_export_root(request: Request):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/export", "")

    @app.api_route("/api/v1/export/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_export_path(request: Request, path: str):
        return await proxy_request(request, EXPENSE_SERVICE_URL, "/api/v1/export", path)

if BUDGET_SERVICE_URL and not GATEWAY_PUBLIC_URL:
    @app.api_route("/api/v1/budgets", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_budgets_root(request: Request):
        return await proxy_request(request, BUDGET_SERVICE_URL, "/api/v1/budgets", "")

    @app.api_route("/api/v1/budgets/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_budgets_path(request: Request, path: str):
        return await proxy_request(request, BUDGET_SERVICE_URL, "/api/v1/budgets", path)

if INVESTMENT_SERVICE_URL and not GATEWAY_PUBLIC_URL:
    @app.api_route("/api/v1/holdings", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_holdings_root(request: Request):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/holdings", "")

    @app.api_route("/api/v1/holdings/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_holdings_path(request: Request, path: str):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/holdings", path)

    @app.api_route("/api/v1/recommendations", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_recommendations_root(request: Request):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/recommendations", "")

    @app.api_route("/api/v1/recommendations/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_recommendations_path(request: Request, path: str):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/recommendations", path)

    @app.api_route("/api/v1/portfolio", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_portfolio_root(request: Request):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/portfolio", "")

    @app.api_route("/api/v1/portfolio/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_portfolio_path(request: Request, path: str):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/portfolio", path)

    @app.api_route("/api/v1/market", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_market_root(request: Request):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/market", "")

    @app.api_route("/api/v1/market/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_market_path(request: Request, path: str):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/market", path)

    @app.api_route("/api/v1/risk-profile", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_risk_profile_root(request: Request):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/risk-profile", "")

    @app.api_route("/api/v1/risk-profile/{path:path}", methods=PROXY_METHODS, include_in_schema=False)
    async def proxy_risk_profile_path(request: Request, path: str):
        return await proxy_request(request, INVESTMENT_SERVICE_URL, "/api/v1/risk-profile", path)


def _render(page: str, request: Request, **context):
    if templates is None:
        raise HTTPException(status_code=503, detail="Frontend not found")
    csp_nonce = str(getattr(request.state, "csp_nonce", "") or "")
    # When using the gateway, pass empty string so the frontend uses same-origin (relative) for all
    # API calls. That way the app works whether the user opened localhost:8080 or 127.0.0.1:8080,
    # and tokens in localStorage apply to the same origin they're actually using.
    expense_api_base = "" if GATEWAY_PUBLIC_URL else EXPENSE_API_BASE_FRONTEND
    budget_api_base = "" if GATEWAY_PUBLIC_URL else BUDGET_API_BASE_FRONTEND
    base_context = {
        "request": request,
        "expense_api_base": expense_api_base,
        "budget_api_base": budget_api_base,
        "gateway_public_url": "",  # always use relative paths; gateway is same-origin when accessed via port 8080
        "plaid_flow": (os.environ.get("PLAID_FLOW", "hosted") or "hosted").strip().lower(),
        "csp_nonce": csp_nonce,
    }
    base_context.update(context)
    return templates.TemplateResponse(page, base_context)


def _db_readiness_check() -> tuple[bool, str | None]:
    try:
        conn = psycopg2.connect(
            host=DB_HOST or "localhost",
            port=int(DB_PORT) if DB_PORT else 5432,
            user=DB_USER or "postgres",
            password=DB_PASSWORD or "postgres",
            dbname=DB_NAME or "users_db",
            connect_timeout=3,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def _extract_user_id(request: Request) -> int | None:
    auth = (request.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if sub is None:
            return None
        return int(sub)
    except Exception:
        return None


def _is_expensive_endpoint(path: str) -> bool:
    for prefix in EXPENSIVE_RATE_LIMIT_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _rate_limited_response(scope: str, decision) -> JSONResponse:
    headers = {
        "Retry-After": str(decision.retry_after_seconds),
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "X-RateLimit-Window": str(decision.window_seconds),
    }
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded",
            "scope": scope,
            "limit": decision.limit,
            "window_seconds": decision.window_seconds,
            "retry_after_seconds": decision.retry_after_seconds,
        },
        headers=headers,
    )


def _log_json(level: str, **fields) -> None:
    line = json.dumps(fields, default=str, separators=(",", ":"))
    if level == "error":
        logger.error(line)
    else:
        logger.info(line)


async def structured_logging_middleware(request: Request, call_next):
    incoming = (request.headers.get("x-request-id") or "").strip()
    request_id = incoming if incoming else str(uuid.uuid4())
    request.state.request_id = request_id
    user_id = _extract_user_id(request)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as e:
        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        payload = {
            "service": "user",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
            "duration_ms": duration_ms,
        }
        if user_id is not None:
            payload["user_id"] = user_id
        _log_json("error", **payload)
        raise
    response.headers["X-Request-ID"] = request_id
    duration_ms = round((time.perf_counter() - start) * 1000, 3)
    payload = {
        "service": "user",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    }
    if user_id is not None:
        payload["user_id"] = user_id
    _log_json("info", **payload)
    return response


async def api_rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    ip = get_client_ip(request)

    if path.startswith("/api/v1/"):
        decision = evaluate_rate_limit(
            key=f"gateway:ip:{ip}",
            max_requests=RATE_LIMIT_API_PER_MINUTE,
        )
        if not decision.allowed:
            return _rate_limited_response("gateway_ip", decision)

    if _is_expensive_endpoint(path):
        user_id = _extract_user_id(request)
        rate_key = f"expensive:user:{user_id}" if user_id is not None else f"expensive:ip:{ip}"
        decision = evaluate_rate_limit(
            key=rate_key,
            max_requests=RATE_LIMIT_EXPENSIVE_PER_USER_PER_MINUTE,
        )
        if not decision.allowed:
            return _rate_limited_response("expensive_user", decision)

    return await call_next(request)


async def security_headers_middleware(request: Request, call_next):
    nonce = uuid.uuid4().hex
    request.state.csp_nonce = nonce
    response = await call_next(request)
    if not SECURITY_HEADERS_ENABLED:
        return response
    csp_policy = CSP_POLICY.replace("{nonce}", nonce)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Content-Security-Policy", csp_policy)
    if HSTS_MAX_AGE_SECONDS > 0:
        response.headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={HSTS_MAX_AGE_SECONDS}; includeSubDomains",
        )
    return response


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
async def ready():
    ok, _ = _db_readiness_check()
    if ok:
        return {"status": "ready"}
    return JSONResponse(status_code=503, content={"status": "not_ready"})


@app.get("/", include_in_schema=False)
async def home(request: Request):
    return _render("landing.html", request)


@app.get("/landing", include_in_schema=False)
async def landing_page(request: Request):
    return _render("landing.html", request)


@app.get("/wireframe", include_in_schema=False)
async def wireframe_page(request: Request):
    """End-to-end HTML wireframe: new user journey, all screens, hash routing."""
    return _render("wireframe.html", request)


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page(request: Request):
    return _render("dashboard.html", request)


@app.get("/welcome", include_in_schema=False)
async def welcome_page(request: Request):
    return _render("welcome.html", request)


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return _render("login.html", request)


@app.get("/register", include_in_schema=False)
async def register_page(request: Request):
    return _render("register.html", request)


@app.get("/forgot-password", include_in_schema=False)
async def forgot_password_page(request: Request):
    return _render("forgot_password.html", request)


@app.get("/reset-password", include_in_schema=False)
async def reset_password_page(request: Request):
    return _render("reset_password.html", request)


@app.get("/verify-email", include_in_schema=False)
async def verify_email(token: str = ""):
    """Validate verification token and redirect to login with result."""
    if token and verify_email_token(token):
        return RedirectResponse(url="/login?verified=1", status_code=302)
    return RedirectResponse(url="/login?verified=0", status_code=302)


@app.get("/expenses", include_in_schema=False)
async def expenses_list_page(request: Request):
    return _render("expenses/list.html", request)


@app.get("/expenses/add", include_in_schema=False)
async def expenses_add_page(request: Request):
    return _render("expenses/add.html", request)


@app.get("/expenses/import", include_in_schema=False)
async def expenses_import_page(request: Request):
    return _render("expenses/import.html", request)


@app.get("/income", include_in_schema=False)
async def income_list_page(request: Request):
    return _render("income/list.html", request)


@app.get("/income/add", include_in_schema=False)
async def income_add_page(request: Request):
    return _render("income/add.html", request)


@app.get("/recurring", include_in_schema=False)
async def recurring_list_page(request: Request):
    return _render("recurring/list.html", request)


@app.get("/expenses/{expense_id}", include_in_schema=False)
async def expense_detail_page(request: Request, expense_id: str):
    """Serve expense detail page; ensure this app (not a static server) runs on your frontend port (e.g. 8000)."""
    return _render("expenses/detail.html", request, expense_id=expense_id)


@app.get("/budgets", include_in_schema=False)
async def budgets_list_page(request: Request):
    return _render("budgets/list.html", request)


@app.get("/budgets/add", include_in_schema=False)
async def budgets_add_page(request: Request):
    return _render("budgets/add.html", request)


@app.get("/budgets/{budget_id}", include_in_schema=False)
async def budget_detail_page(request: Request, budget_id: str):
    return _render("budgets/detail.html", request, budget_id=budget_id)


@app.get("/user/{user_id}/budgets", include_in_schema=False)
async def user_budgets_redirect(user_id: str):
    """HATEOAS: resolve /user/{id}/budgets to the budgets list page."""
    return RedirectResponse(url="/budgets", status_code=302)


@app.get("/reports", include_in_schema=False)
async def reports_page(request: Request):
    return _render("reports.html", request)


@app.get("/insights", include_in_schema=False)
async def insights_page(request: Request):
    return _render("insights.html", request)


@app.get("/reports/category/{category_code}", include_in_schema=False)
async def reports_category_page(request: Request, category_code: str):
    return _render("reports_category.html", request, category_code=category_code)


@app.get("/goals", include_in_schema=False)
async def savings_goals_page(request: Request):
    return _render("savings_goals.html", request)


@app.get("/goals/add", include_in_schema=False)
async def goal_add_page(request: Request):
    return _render("goal_add.html", request)


@app.get("/goals/{goal_id}", include_in_schema=False)
async def goal_detail_page(request: Request, goal_id: str):
    return _render("goal_detail.html", request, goal_id=goal_id)


@app.get("/settings/integrations", include_in_schema=False)
async def integrations_page(request: Request):
    return _render("settings/integrations.html", request)


@app.get("/investments", include_in_schema=False)
async def investments_page(request: Request):
    return _render("investments.html", request)


@app.get("/recommendations", include_in_schema=False)
async def recommendations_page(request: Request):
    return _render("recommendations.html", request)


@app.get("/link-bank", include_in_schema=False)
async def link_bank_page(request: Request):
    return _render("link_bank.html", request)


@app.get("/link-bank/success", include_in_schema=False)
async def link_bank_success_page(request: Request):
    return _render("link_bank_success.html", request)


@app.get("/link-bank/select", include_in_schema=False)
async def link_bank_select_page(request: Request):
    return _render("link_bank_select.html", request)


@app.get("/net-worth", include_in_schema=False)
async def net_worth_page(request: Request):
    return _render("net_worth.html", request)


@app.get("/notifications", include_in_schema=False)
async def notifications_page(request: Request):
    return _render("notifications.html", request)


@app.get("/household", include_in_schema=False)
async def household_page(request: Request):
    return _render("household.html", request)


@app.get("/sessions", include_in_schema=False)
async def sessions_page(request: Request):
    return _render("sessions.html", request)


@app.get("/profile", include_in_schema=False)
async def profile_page(request: Request):
    return _render("profile.html", request)


@app.get("/settings", include_in_schema=False)
async def settings_page(request: Request):
    return _render("settings.html", request)


@app.get("/saved-views", include_in_schema=False)
async def saved_views_page(request: Request):
    return _render("saved_views.html", request)


@app.get("/verify-email/pending", include_in_schema=False)
async def verify_email_pending_page(request: Request, email: Optional[str] = None):
    return _render("verify_email_pending.html", request, email=email or "")


app.middleware("http")(security_headers_middleware)
app.middleware("http")(api_rate_limit_middleware)
app.middleware("http")(structured_logging_middleware)


if __name__ == "__main__":
    # Run on 8000 so /expenses and /expenses/{id} are both served; use: python -m app.main
    uvicorn.run(app, host="0.0.0.0", port=8000)
