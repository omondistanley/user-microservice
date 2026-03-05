from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# Allow running without app installed as package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.expenses as expenses_router
import app.routers.income as income_router
from app.core.dependencies import get_current_user_id
from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user_id] = lambda: 1
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


def test_expense_summary_conversion_math(auth_override, monkeypatch):
    class FakeDataService:
        def get_expense_summary_by_currency(self, user_id, group_by, date_from=None, date_to=None):
            assert user_id == 1
            assert group_by == "category"
            return [
                {
                    "group_key": "1",
                    "label": "Food",
                    "currency": "EUR",
                    "total_amount": Decimal("10"),
                    "count": 1,
                },
                {
                    "group_key": "1",
                    "label": "Food",
                    "currency": "USD",
                    "total_amount": Decimal("5"),
                    "count": 1,
                },
            ]

        def convert_amount(self, amount, from_currency, to_currency, as_of_date=None):
            if from_currency == "EUR" and to_currency == "USD":
                return {
                    "converted_amount": Decimal("11.0000"),
                    "rate_date": date(2026, 2, 27),
                    "source": "ECB",
                }
            if from_currency == "USD" and to_currency == "USD":
                return {
                    "converted_amount": Decimal("5.0000"),
                    "rate_date": date(2026, 2, 27),
                    "source": "identity",
                }
            return None

    monkeypatch.setattr(expenses_router, "_get_expense_data_service", lambda: FakeDataService())
    r = client.get("/api/v1/expenses/summary?group_by=category&convert_to=USD")
    assert r.status_code == 200
    body = r.json()
    assert body["group_by"] == "category"
    assert body["convert_to"] == "USD"
    assert len(body["items"]) == 1
    assert Decimal(str(body["items"][0]["total_amount"])) == Decimal("16.0000")


def test_expense_summary_conversion_missing_rate_returns_422(auth_override, monkeypatch):
    class FakeDataService:
        def get_expense_summary_by_currency(self, user_id, group_by, date_from=None, date_to=None):
            return [
                {
                    "group_key": "1",
                    "label": "Food",
                    "currency": "KES",
                    "total_amount": Decimal("1000"),
                    "count": 1,
                }
            ]

        def convert_amount(self, amount, from_currency, to_currency, as_of_date=None):
            return None

    monkeypatch.setattr(expenses_router, "_get_expense_data_service", lambda: FakeDataService())
    r = client.get("/api/v1/expenses/summary?group_by=category&convert_to=USD")
    assert r.status_code == 422
    assert "Missing exchange rate" in r.text


def test_cashflow_summary_conversion_math(auth_override, monkeypatch):
    class FakeDataService:
        def get_income_totals_by_currency(self, user_id, date_from=None, date_to=None):
            return [
                {"currency": "EUR", "total_amount": Decimal("100"), "count": 1},
                {"currency": "USD", "total_amount": Decimal("50"), "count": 1},
            ]

        def get_expense_totals_by_currency(self, user_id, date_from=None, date_to=None):
            return [
                {"currency": "EUR", "total_amount": Decimal("30"), "count": 1},
                {"currency": "USD", "total_amount": Decimal("20"), "count": 1},
            ]

        def convert_amount(self, amount, from_currency, to_currency, as_of_date=None):
            if from_currency == to_currency:
                return {
                    "converted_amount": Decimal(str(amount)),
                    "rate_date": date(2026, 2, 27),
                    "source": "identity",
                }
            if from_currency == "EUR" and to_currency == "USD":
                return {
                    "converted_amount": (Decimal(str(amount)) * Decimal("1.1")).quantize(Decimal("0.0001")),
                    "rate_date": date(2026, 2, 27),
                    "source": "ECB",
                }
            return None

    monkeypatch.setattr(income_router, "_get_data_service", lambda: FakeDataService())
    r = client.get("/api/v1/cashflow/summary?convert_to=USD")
    assert r.status_code == 200
    body = r.json()
    assert body["convert_to"] == "USD"
    assert Decimal(str(body["income_total"])) == Decimal("160.0000")
    assert Decimal(str(body["expense_total"])) == Decimal("53.0000")
    assert Decimal(str(body["savings"])) == Decimal("107.0000")
