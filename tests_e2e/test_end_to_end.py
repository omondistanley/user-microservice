import os
import time
from decimal import Decimal

import pytest
import requests


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