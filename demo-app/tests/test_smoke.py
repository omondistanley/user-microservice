"""Smoke tests for demo app."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.auth_demo import COOKIE_NAME, verify_demo_token
from app.db import list_budgets, list_expenses_for_month


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("service") == "pocketii-demo"


def test_demo_landing(client):
    assert client.get("/demo").status_code == 200


def test_watch_page(client):
    assert client.get("/demo/watch").status_code == 200


def test_session_and_expense(client):
    r = client.post("/demo/session")
    assert r.status_code == 200
    jar = r.cookies
    d = client.get("/demo/app/dashboard", cookies=jar)
    assert d.status_code == 200
    e = client.post(
        "/api/demo/expenses",
        cookies=jar,
        json={"amount": 9.99, "description": "test"},
    )
    assert e.status_code == 200


def test_narrate_disabled_by_default(client):
    r = client.post("/demo/narrate", json={"scene_id": "intro"})
    assert r.status_code == 503


def _start_session(client: TestClient):
    r = client.post("/demo/session")
    assert r.status_code == 200
    return r.cookies


def _sid_from_cookies(cookies):
    token = cookies.get(COOKIE_NAME)
    payload = verify_demo_token(token)
    assert payload and payload.get("demo") is True
    return str(payload["sid"])


def test_session_scoping_and_expense_edit(client):
    jar1 = _start_session(client)
    jar2 = _start_session(client)

    e1 = client.post(
        "/api/demo/expenses",
        cookies=jar1,
        json={"amount": 9.99, "description": "test-jar1", "category": "Food", "expense_date": "2026-03-10"},
    )
    assert e1.status_code == 200
    e1_id = e1.json()["id"]

    e2 = client.post(
        "/api/demo/expenses",
        cookies=jar2,
        json={"amount": 4.50, "description": "test-jar2", "category": "Transit", "expense_date": "2026-03-11"},
    )
    assert e2.status_code == 200

    r1 = client.get("/api/demo/expenses", cookies=jar1)
    r2 = client.get("/api/demo/expenses", cookies=jar2)
    assert r1.status_code == 200
    assert r2.status_code == 200

    list1 = r1.json()["expenses"]
    list2 = r2.json()["expenses"]
    assert any(x["id"] == e1_id for x in list1)
    assert all(x["description"] != "test-jar1" for x in list2)

    # edit jar1 expense
    upd = client.post(
        f"/api/demo/expenses/{e1_id}",
        cookies=jar1,
        json={"amount": 10.25, "description": "edited-jar1", "category": "Food", "expense_date": "2026-03-12"},
    )
    assert upd.status_code == 200

    list1_after = client.get("/api/demo/expenses", cookies=jar1).json()["expenses"]
    assert any(x["description"] == "edited-jar1" for x in list1_after)


def test_month_based_budget_computation(client):
    jar = _start_session(client)
    sid = _sid_from_cookies(jar)

    # One expense in 2026-03 and one expense in 2026-02.
    r_march = client.post(
        "/api/demo/expenses",
        cookies=jar,
        json={"amount": 100.00, "description": "March food", "category": "Food", "expense_date": "2026-03-10"},
    )
    assert r_march.status_code == 200
    r_feb = client.post(
        "/api/demo/expenses",
        cookies=jar,
        json={"amount": 200.00, "description": "Feb food", "category": "Food", "expense_date": "2026-02-10"},
    )
    assert r_feb.status_code == 200

    # Budget for March only
    b = client.post(
        "/api/demo/budgets",
        cookies=jar,
        json={"month": "2026-03", "category": "Food", "limit": 150.00},
    )
    assert b.status_code == 200

    budgets = list_budgets(sid, "2026-03")
    assert len(budgets) >= 1
    budget_food = [x for x in budgets if x["category"] == "Food"][0]

    march_expenses = list_expenses_for_month(sid, "2026-03")
    march_food_spent = sum(x["amount"] for x in march_expenses if x["category"] == "Food")
    assert march_food_spent == 100.00

    # Remaining: 150 - 100 = 50
    remaining = float(budget_food["limit"]) - float(march_food_spent)
    assert remaining == 50.00

    # Ensure budgets page renders the computed remaining
    page = client.get("/demo/app/budgets?month=2026-03", cookies=jar)
    assert page.status_code == 200
    assert "$50.00" in page.text


def test_watch_pages_are_read_only_and_api_requires_jwt(client):
    # Watch routes should be accessible without a demo JWT.
    assert client.get("/demo/watch/app/dashboard").status_code == 200
    assert client.get("/demo/watch/app/expenses").status_code == 200
    assert client.get("/demo/watch/app/expenses/add").status_code == 200
    assert client.get("/demo/watch/app/expenses/detail/coffee").status_code == 200
    assert client.get("/demo/watch/app/budgets").status_code == 200
    assert client.get("/demo/watch/app/budgets/add").status_code == 200
    assert client.get("/demo/watch/app/budgets/add?month=2026-03").status_code == 200
    assert client.get("/demo/watch/app/budgets/detail/food_2026_03").status_code == 200
    assert client.get("/demo/watch/app/insights").status_code == 200
    assert client.get("/demo/watch/app/recommendations").status_code == 200
    assert client.get("/demo/watch/app/investments").status_code == 200

    # Mutations should require the demo JWT cookie.
    assert client.post("/api/demo/expenses", json={"amount": 1, "description": "x"}).status_code == 401
    assert client.post(
        "/api/demo/budgets",
        json={"month": "2026-03", "category": "Food", "limit": 10.0},
    ).status_code == 401

    assert client.post("/api/demo/recommendations/run", json={"month": "2026-03"}).status_code == 401


def test_interactive_insights_and_recommendations_exist(client):
    jar = _start_session(client)
    assert client.get("/demo/app/insights?month=2026-03", cookies=jar).status_code == 200
    assert (
        client.get("/demo/app/recommendations?month=2026-03", cookies=jar).status_code == 200
    )


def test_new_app_routes_require_demo_and_return_200(client):
    """New parity routes: require demo session and return 200 with expected content."""
    # Without cookie, should redirect to demo/start
    r = client.get("/demo/app/net-worth", follow_redirects=False)
    assert r.status_code == 302
    assert "demo/start" in (r.headers.get("location") or "")

    jar = _start_session(client)
    routes_and_text = [
        ("/demo/app/net-worth", "Net Worth"),
        ("/demo/app/income", "Income"),
        ("/demo/app/income/add", "Add income"),
        ("/demo/app/recurring", "Recurring"),
        ("/demo/app/goals", "Savings Goals"),
        ("/demo/app/goals/add", "New goal"),
        ("/demo/app/reports", "Reports"),
        ("/demo/app/notifications", "Notifications"),
        ("/demo/app/household", "Household"),
        ("/demo/app/sessions", "Sessions"),
        ("/demo/app/profile", "Profile"),
        ("/demo/app/settings", "Settings"),
        ("/demo/app/saved-views", "Saved Views"),
        ("/demo/app/link-bank", "Link Bank"),
        ("/demo/app/link-bank/success", "Demo only"),
        ("/demo/app/settings/integrations", "Integrations"),
    ]
    for path, expected in routes_and_text:
        resp = client.get(path, cookies=jar)
        assert resp.status_code == 200, f"GET {path} returned {resp.status_code}"
        assert expected in resp.text, f"GET {path} missing expected text {expected!r}"


def test_income_and_goals_api(client):
    jar = _start_session(client)
    # Income
    r = client.get("/api/demo/income", cookies=jar)
    assert r.status_code == 200
    assert "income" in r.json()
    r2 = client.post(
        "/api/demo/income",
        cookies=jar,
        json={"amount": 1500.0, "source": "Salary", "income_date": "2026-03-01"},
    )
    assert r2.status_code == 200
    assert r2.json().get("ok") is True
    # Goals
    r3 = client.get("/api/demo/goals", cookies=jar)
    assert r3.status_code == 200
    assert "goals" in r3.json()
    r4 = client.post(
        "/api/demo/goals",
        cookies=jar,
        json={"name": "Emergency fund", "target_amount": 5000.0, "current_amount": 500.0},
    )
    assert r4.status_code == 200
    assert r4.json().get("ok") is True


def test_integrations_redirect(client):
    jar = _start_session(client)
    r = client.get("/demo/app/integrations", cookies=jar, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/demo/app/settings/integrations"
