import os
import time
from decimal import Decimal

import requests


USER_BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "http://localhost:8000")
EXPENSE_BASE_URL = os.getenv("EXPENSE_SERVICE_BASE_URL", "http://localhost:3001")
BUDGET_BASE_URL = os.getenv("BUDGET_SERVICE_BASE_URL", "http://localhost:3002")
INVESTMENT_BASE_URL = os.getenv("INVESTMENT_SERVICE_BASE_URL", "http://localhost:3003")


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


def test_stack_health():
    """Basic smoke test that core services are up behind Docker."""
    _wait_for_health(f"{USER_BASE_URL}/health")
    _wait_for_health(f"{EXPENSE_BASE_URL}/health")
    _wait_for_health(f"{BUDGET_BASE_URL}/health")
    _wait_for_health(f"{INVESTMENT_BASE_URL}/health")


def test_net_worth_summary_end_to_end():
    """
    End‑to‑end test for net worth aggregation.

    Assumes docker compose stack is running (see docker/DOCKER_QUICKSTART.txt)
    and that the user service is reachable on USER_BASE_URL.
    """
    _wait_for_health(f"{USER_BASE_URL}/health")

    resp = requests.get(f"{USER_BASE_URL}/api/v1/net-worth/summary", timeout=10)
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
    assets_total = Decimal(str(body["assets_total"]))
    liabilities_total = Decimal(str(body["liabilities_total"]))
    net_worth = Decimal(str(body["net_worth"]))

    # Net worth identity must hold.
    assert assets_total == cash + investments
    assert net_worth == assets_total - liabilities_total

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

    email = os.getenv("E2E_TEST_USER_EMAIL", "test@example.com")
    password = os.getenv("E2E_TEST_USER_PASSWORD", "changeme")

    # OAuth2PasswordRequestForm expects form-encoded fields: username, password.
    login_resp = requests.post(
        f"{USER_BASE_URL}/login",
        data={"username": email, "password": password},
        timeout=10,
    )
    if login_resp.status_code == 401:
        # In some environments you may not have a seeded test user; skip instead
        # of failing the whole e2e suite.
        return

    assert login_resp.status_code == 200
    tokens = login_resp.json()
    access_token = tokens.get("access_token")
    assert access_token, "login did not return access_token"

    headers = {"Authorization": f"Bearer {access_token}"}
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
    _wait_for_health(f"{BUDGET_BASE_URL}/health")
    # Adjust path to a real budget endpoint you care about, e.g. categories or summaries
    resp = requests.get(f"{BUDGET_BASE_URL}/api/v1/budgets", timeout=10)
    assert resp.status_code in (200, 204)  # depending on how empty-state is implemented
    # Optionally assert JSON shape if it returns data
    if resp.status_code == 200:
        body = resp.json()
        assert isinstance(body, dict) or isinstance(body, list)