from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# Allow running without app installed as package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.income as income_router
import app.routers.recurring_expenses as recurring_router
from app.core.dependencies import get_current_user_id
from app.main import app
from app.models.expenses import ExpenseResponse


client = TestClient(app)


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user_id] = lambda: 1
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


def test_openapi_includes_phase1_v1_routes():
    spec = app.openapi()
    paths = spec.get("paths", {})
    assert "/api/v1/income" in paths
    assert "/api/v1/income/summary" in paths
    assert "/api/v1/cashflow/summary" in paths
    assert "/api/v1/recurring-expenses" in paths
    assert "/api/v1/recurring-expenses/{recurring_id}/run" in paths
    assert "/api/v1/expenses/export" in paths


def test_income_summary_happy_path(auth_override, monkeypatch):
    class FakeDataService:
        def get_income_summary(self, user_id, group_by, date_from=None, date_to=None):
            assert user_id == 1
            assert group_by == "month"
            return [
                {
                    "group_key": "2026-02",
                    "label": "2026-02",
                    "total_amount": Decimal("2500.00"),
                    "count": 2,
                }
            ]

    monkeypatch.setattr(income_router, "_get_data_service", lambda: FakeDataService())
    r = client.get("/api/v1/income/summary?group_by=month&date_from=2026-02-01&date_to=2026-02-28")
    assert r.status_code == 200
    body = r.json()
    assert body["group_by"] == "month"
    assert len(body["items"]) == 1
    assert body["items"][0]["group_key"] == "2026-02"
    assert Decimal(str(body["items"][0]["total_amount"])) == Decimal("2500.00")
    assert body["items"][0]["count"] == 2


def test_cashflow_summary_happy_path(auth_override, monkeypatch):
    class FakeDataService:
        def get_income_total(self, user_id, date_from=None, date_to=None):
            assert user_id == 1
            return Decimal("2500.00")

        def get_expense_total(self, user_id, date_from=None, date_to=None):
            assert user_id == 1
            return Decimal("1750.00")

    monkeypatch.setattr(income_router, "_get_data_service", lambda: FakeDataService())
    r = client.get("/api/v1/cashflow/summary?date_from=2026-02-01&date_to=2026-02-28")
    assert r.status_code == 200
    body = r.json()
    assert Decimal(str(body["income_total"])) == Decimal("2500.00")
    assert Decimal(str(body["expense_total"])) == Decimal("1750.00")
    assert Decimal(str(body["savings"])) == Decimal("750.00")


def test_income_invalid_uuid_returns_400(auth_override):
    r = client.get("/api/v1/income/not-a-uuid")
    assert r.status_code == 400
    assert "Invalid income id" in r.text


def test_recurring_run_happy_path(auth_override, monkeypatch):
    recurring_id = str(uuid4())
    created_expense_id = uuid4()
    now = datetime.now(timezone.utc)
    base_recurring = {
        "recurring_id": recurring_id,
        "user_id": 1,
        "amount": Decimal("49.99"),
        "currency": "USD",
        "category_code": 1,
        "category_name": "Food",
        "description": "Meal plan",
        "recurrence_rule": "monthly",
        "next_due_date": date(2026, 2, 15),
        "last_run_at": None,
        "last_created_expense_id": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    class FakeDataService:
        def get_recurring_expense_by_id(self, rid, user_id):
            assert rid == recurring_id
            assert user_id == 1
            return dict(base_recurring)

        def update_recurring_expense(self, rid, user_id, updates):
            assert rid == recurring_id
            assert user_id == 1
            updated = dict(base_recurring)
            updated["next_due_date"] = date(2026, 3, 15)
            updated["last_run_at"] = updates.get("last_run_at")
            updated["last_created_expense_id"] = updates.get("last_created_expense_id")
            updated["updated_at"] = updates.get("updated_at") or now
            return updated

    class FakeExpenseResource:
        def create(self, user_id, payload, source=None, plaid_transaction_id=None):
            assert user_id == 1
            assert source == "recurring"
            assert payload.category_code == 1
            return ExpenseResponse(
                expense_id=created_expense_id,
                user_id=1,
                category_code=1,
                category_name="Food",
                amount=Decimal("49.99"),
                date=date(2026, 2, 15),
                currency="USD",
                description="Meal plan",
                balance_after=Decimal("199.99"),
                created_at=now,
                updated_at=now,
                source="recurring",
                plaid_transaction_id=None,
            )

    monkeypatch.setattr(recurring_router, "_get_data_service", lambda: FakeDataService())
    monkeypatch.setattr(recurring_router, "_get_expense_resource", lambda: FakeExpenseResource())
    r = client.post(f"/api/v1/recurring-expenses/{recurring_id}/run")
    assert r.status_code == 200
    body = r.json()
    assert body["recurring"]["next_due_date"] == "2026-03-15"
    assert body["created_expense"]["source"] == "recurring"
    assert body["created_expense"]["expense_id"] == str(created_expense_id)


def test_recurring_run_invalid_uuid_returns_400(auth_override):
    r = client.post("/api/v1/recurring-expenses/not-a-uuid/run")
    assert r.status_code == 400
    assert "Invalid recurring expense id" in r.text


def test_recurring_run_inactive_returns_400(auth_override, monkeypatch):
    recurring_id = str(uuid4())
    now = datetime.now(timezone.utc)

    class FakeDataService:
        def get_recurring_expense_by_id(self, rid, user_id):
            return {
                "recurring_id": recurring_id,
                "user_id": 1,
                "amount": Decimal("19.99"),
                "currency": "USD",
                "category_code": 1,
                "category_name": "Food",
                "description": "Inactive plan",
                "recurrence_rule": "monthly",
                "next_due_date": date(2026, 2, 15),
                "last_run_at": None,
                "last_created_expense_id": None,
                "is_active": False,
                "created_at": now,
                "updated_at": now,
            }

    monkeypatch.setattr(recurring_router, "_get_data_service", lambda: FakeDataService())
    r = client.post(f"/api/v1/recurring-expenses/{recurring_id}/run")
    assert r.status_code == 400
    assert "inactive" in r.text.lower()
