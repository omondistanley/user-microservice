import os
import time
import uuid
from decimal import Decimal

import pytest
import requests


GATEWAY_BASE_URL = os.getenv("GATEWAY_BASE_URL", "http://localhost:8080")
USER_BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "http://localhost:8000")
EXPENSE_BASE_URL = os.getenv("EXPENSE_SERVICE_BASE_URL", "http://localhost:3001")
BUDGET_BASE_URL = os.getenv("BUDGET_SERVICE_BASE_URL", "http://localhost:3002")
INVESTMENT_BASE_URL = os.getenv("INVESTMENT_SERVICE_BASE_URL", "http://localhost:3003")


def _e2e_auth_headers() -> dict[str, str] | None:
    """
    Log in with E2E_TEST_USER_EMAIL / E2E_TEST_USER_PASSWORD and return Authorization headers.

    Returns None if credentials are rejected (401), so callers can pytest.skip when no seeded user.
    """
    email = os.getenv("E2E_TEST_USER_EMAIL", "test@example.com")
    password = os.getenv("E2E_TEST_USER_PASSWORD", "changeme")
    login_resp = requests.post(
        f"{USER_BASE_URL}/login",
        data={"username": email, "password": password},
        timeout=10,
    )
    if login_resp.status_code == 401:
        return None
    if login_resp.status_code != 200:
        pytest.skip(
            f"E2E login failed with status {login_resp.status_code}; "
            "check USER_SERVICE_BASE_URL and seeded user."
        )
    tokens = login_resp.json()
    access_token = tokens.get("access_token")
    if not access_token:
        pytest.skip("Login succeeded but no access_token in response")
    return {"Authorization": f"Bearer {access_token}"}


def _wait_for_health(url: str, timeout_seconds: int = 60) -> None:
    """Poll a /health endpoint until it returns 200 or timeout."""
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return
        except Exception as exc:  # pragma: no cover - best‑effort wait helper
            last_error = exc
        time.sleep(1)
    if last_error:
        raise RuntimeError(f"Service at {url} did not become healthy") from last_error
    raise RuntimeError(f"Service at {url} did not become healthy")


def _gateway_login_headers(email: str, password: str) -> dict[str, str] | None:
    payload = _gateway_login_payload(email, password)
    if payload is None:
        return None
    token = payload.get("access_token")
    if not token:
        pytest.skip("Gateway login succeeded but no access_token was returned")
    return {"Authorization": f"Bearer {token}"}


def _gateway_login_payload(email: str, password: str) -> dict[str, str] | None:
    resp = requests.post(
        f"{GATEWAY_BASE_URL}/login",
        data={"username": email, "password": password},
        timeout=10,
    )
    if resp.status_code == 401:
        return None
    if resp.status_code == 403:
        pytest.skip("Gateway login requires email verification in this environment.")
    if resp.status_code != 200:
        pytest.skip(f"Gateway login failed with status {resp.status_code}")
    return resp.json()


def _ensure_gateway_user_headers() -> dict[str, str]:
    email = os.getenv("E2E_TEST_USER_EMAIL", "").strip()
    password = os.getenv("E2E_TEST_USER_PASSWORD", "").strip()
    if email and password:
        headers = _gateway_login_headers(email, password)
        if headers:
            return headers

    email, password = _register_gateway_user()
    headers = _gateway_login_headers(email, password)
    if not headers:
        pytest.skip("Fresh gateway user could not log in.")
    return headers


def _register_gateway_user() -> tuple[str, str]:
    unique = uuid.uuid4().hex[:10]
    email = f"gateway-e2e-{unique}@example.com"
    password = f"ChangeMe-{unique}!"
    register = requests.post(
        f"{GATEWAY_BASE_URL}/user",
        json={
            "email": email,
            "first_name": "Gateway",
            "last_name": "E2E",
            "password": password,
        },
        timeout=10,
    )
    if register.status_code not in (200, 201):
        pytest.skip(f"Gateway registration failed with status {register.status_code}")
    return email, password


def test_stack_health():
    """Basic smoke test that core services are up behind Docker."""
    _wait_for_health(f"{GATEWAY_BASE_URL}/health")
    _wait_for_health(f"{USER_BASE_URL}/health")
    _wait_for_health(f"{EXPENSE_BASE_URL}/health")
    _wait_for_health(f"{BUDGET_BASE_URL}/health")
    _wait_for_health(f"{INVESTMENT_BASE_URL}/health")


def test_gateway_public_first_run_pages():
    _wait_for_health(f"{GATEWAY_BASE_URL}/health")

    checks = [
        ("/landing", "pocketii"),
        ("/register", "Create account"),
        ("/login", "Welcome back"),
        ("/forgot-password", "Forgot password"),
        ("/verify-email/pending", "Check your inbox"),
        ("/dashboard", "Running Balance"),
        ("/expenses/add", "Add"),
        ("/budgets/add", "Add budget"),
        ("/goals/add", "New Savings Goal"),
        ("/link-bank", "Link"),
        ("/settings/integrations", "Integrations"),
        ("/investments", "Investments"),
        ("/recommendations", "Recommendations"),
    ]

    for path, needle in checks:
        resp = requests.get(f"{GATEWAY_BASE_URL}{path}", timeout=10)
        assert resp.status_code == 200, path
        assert needle.lower() in resp.text.lower(), path


def test_gateway_login_and_refresh_contract():
    _wait_for_health(f"{GATEWAY_BASE_URL}/health")

    email = os.getenv("E2E_TEST_USER_EMAIL", "").strip()
    password = os.getenv("E2E_TEST_USER_PASSWORD", "").strip()
    if not email or not password:
        email, password = _register_gateway_user()

    login_payload = _gateway_login_payload(email, password)
    if login_payload is None:
        pytest.skip("Gateway login credentials were rejected.")

    access_token = login_payload.get("access_token")
    refresh_token = login_payload.get("refresh_token")
    assert access_token
    assert refresh_token

    refresh_resp = requests.post(
        f"{GATEWAY_BASE_URL}/token/refresh",
        json={"refresh_token": refresh_token},
        timeout=10,
    )
    assert refresh_resp.status_code == 200, refresh_resp.text
    refreshed_payload = refresh_resp.json()
    assert refreshed_payload.get("access_token")
    assert refreshed_payload.get("refresh_token")


def test_gateway_first_time_core_mutation_flow():
    _wait_for_health(f"{GATEWAY_BASE_URL}/health")
    headers = _ensure_gateway_user_headers()

    expense_resp = requests.post(
        f"{GATEWAY_BASE_URL}/api/v1/expenses",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "amount": 12.34,
            "category_code": 1,
            "date": "2026-03-27",
            "currency": "USD",
            "description": "Gateway E2E coffee",
        },
        timeout=10,
    )
    assert expense_resp.status_code == 200, expense_resp.text

    budget_resp = requests.post(
        f"{GATEWAY_BASE_URL}/api/v1/budgets",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "name": "Gateway E2E Food",
            "amount": 200,
            "category_code": 1,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "alert_thresholds": [80, 100],
            "alert_channel": "in_app",
        },
        timeout=10,
    )
    assert budget_resp.status_code == 200, budget_resp.text

    goal_resp = requests.post(
        f"{GATEWAY_BASE_URL}/api/v1/goals",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "name": "Gateway E2E Goal",
            "target_amount": 500,
            "target_currency": "USD",
            "start_amount": 25,
        },
        timeout=10,
    )
    assert goal_resp.status_code == 200, goal_resp.text

    expenses = requests.get(f"{GATEWAY_BASE_URL}/api/v1/expenses?page=1&page_size=20", headers=headers, timeout=10)
    budgets = requests.get(f"{GATEWAY_BASE_URL}/api/v1/budgets?page=1&page_size=20", headers=headers, timeout=10)
    goals = requests.get(f"{GATEWAY_BASE_URL}/api/v1/goals?page=1&page_size=20", headers=headers, timeout=10)

    assert expenses.status_code == 200
    assert budgets.status_code == 200
    assert goals.status_code == 200

    expense_items = expenses.json().get("items", [])
    budget_items = budgets.json().get("items", [])
    goal_items = goals.json().get("items", [])

    assert any("Gateway E2E coffee" in str(item.get("description", "")) for item in expense_items)
    assert any(item.get("name") == "Gateway E2E Food" for item in budget_items)
    assert any(item.get("name") == "Gateway E2E Goal" for item in goal_items)


def test_gateway_core_authenticated_contracts():
    _wait_for_health(f"{GATEWAY_BASE_URL}/health")
    headers = _ensure_gateway_user_headers()

    checks = [
        "/user/me",
        "/api/v1/settings",
        "/api/v1/expenses?page=1&page_size=1",
        "/api/v1/transactions?page=1&page_size=1",
        "/api/v1/budgets?page=1&page_size=1",
        "/api/v1/goals?page=1&page_size=1",
        "/api/v1/portfolio/value",
        "/api/v1/recommendations/latest?page=1&page_size=1",
    ]

    for path in checks:
        resp = requests.get(f"{GATEWAY_BASE_URL}{path}", headers=headers, timeout=10)
        assert resp.status_code == 200, f"{path}: {resp.text}"


def test_net_worth_summary_end_to_end():
    """
    End‑to‑end test for net worth aggregation.

    Assumes docker compose stack is running (see docker/DOCKER_QUICKSTART.txt)
    and that the user service is reachable on USER_BASE_URL.
    """
    _wait_for_health(f"{USER_BASE_URL}/health")

    headers = _e2e_auth_headers()
    if headers is None:
        pytest.skip(
            "Net worth summary requires auth. Seed a user or set E2E_TEST_USER_EMAIL / "
            "E2E_TEST_USER_PASSWORD to match docker/env."
        )

    resp = requests.get(
        f"{USER_BASE_URL}/api/v1/net-worth/summary",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code == 200
    body = resp.json()

    # Basic shape checks
    assert "assets" in body
    assert "liabilities" in body
    assert "assets_total" in body
    assert "liabilities_total" in body
    assert "net_worth" in body

    assets = body["assets"]
    liabilities = body["liabilities"]

    cash = Decimal(str(assets.get("cash", "0")))
    investments = Decimal(str(assets.get("investments", "0")))
    budgets = Decimal(str(assets.get("budgets", "0")))
    manual_assets = Decimal(str(assets.get("manual", "0")))
    assets_total = Decimal(str(body["assets_total"]))
    liabilities_total = Decimal(str(body["liabilities_total"]))
    net_worth = Decimal(str(body["net_worth"]))

    # Net worth identity: balance-sheet total excludes contextual income (cashflow window).
    assert assets_total == cash + investments + budgets + manual_assets
    assert net_worth == assets_total - liabilities_total
    assert "warnings" in body
    assert isinstance(body["warnings"], list)

    # Regression: ensure cashflow fields are not part of the computation path.
    as_text = str(body)
    assert "income_total" not in as_text
    assert "expense_total" not in as_text
    assert "savings" not in as_text


def test_budget_list_with_auth_round_trip():
    """
    End‑to‑end test that exercises auth + budget API.

    This assumes:
    - A test user already exists with email/password configured, OR
    - You run this against an environment where /login is wired to a known user.

    It validates:
    - /login issues a bearer token.
    - /api/v1/budgets responds for an authenticated request.
    """
    _wait_for_health(f"{USER_BASE_URL}/health")
    _wait_for_health(f"{BUDGET_BASE_URL}/health")

    headers = _e2e_auth_headers()
    if headers is None:
        pytest.skip(
            "No E2E user credentials or login returned 401; set E2E_TEST_USER_EMAIL / "
            "E2E_TEST_USER_PASSWORD"
        )

    budgets_resp = requests.get(
        f"{BUDGET_BASE_URL}/api/v1/budgets",
        headers=headers,
        timeout=10,
    )
    # 200 with JSON payload is the expected happy path, but allow 204 for empty.
    assert budgets_resp.status_code in (200, 204)
    if budgets_resp.status_code == 200:
        body = budgets_resp.json()
        assert isinstance(body, dict)
        assert "items" in body and "total" in body


def test_budget_api_smoke():
    _wait_for_health(f"{USER_BASE_URL}/health")
    _wait_for_health(f"{BUDGET_BASE_URL}/health")
    headers = _e2e_auth_headers()
    if headers is None:
        pytest.skip(
            "Budget API requires auth. Seed a user or set E2E_TEST_USER_EMAIL / "
            "E2E_TEST_USER_PASSWORD"
        )
    # Adjust path to a real budget endpoint you care about, e.g. categories or summaries
    resp = requests.get(
        f"{BUDGET_BASE_URL}/api/v1/budgets",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code in (200, 204)  # depending on how empty-state is implemented
    # Optionally assert JSON shape if it returns data
    if resp.status_code == 200:
        body = resp.json()
        assert isinstance(body, dict) or isinstance(body, list)
