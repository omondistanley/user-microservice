from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.apple_wallet_webhook as webhook_router
from app.main import app
from app.services.transaction_classifier import classify_transaction


client = TestClient(app)


def test_classifier_maps_nyc_transit_to_transport():
    result = classify_transaction(
        amount=Decimal("12.50"),
        merchant="MTA OMNY",
        note="subway ride",
        flow_type_hint=None,
    )
    assert result.flow_type == "expense"
    assert result.category_hint == "expense_transport"
    assert result.category_code == 2


def test_classifier_maps_salary_to_income():
    result = classify_transaction(
        amount=Decimal("4500.00"),
        merchant="ACME Payroll",
        note="salary march",
        flow_type_hint=None,
    )
    assert result.flow_type == "income"
    assert result.category_hint == "income_salary_other"
    assert result.income_type == "salary"


def test_apple_wallet_webhook_creates_expense_with_transport_hint(monkeypatch):
    class FakeDataService:
        def get_expense_by_apple_wallet_transaction_id(self, user_id, tx_id):
            assert user_id == 77
            assert tx_id == "tx-1"
            return None

        def get_income_by_apple_wallet_transaction_id(self, user_id, tx_id):
            return None

        def update_apple_wallet_last_sync(self, user_id, ts):
            pass

        def get_recent_apple_wallet_expense_match(self, **kwargs):
            return None

        def get_recent_apple_wallet_income_match(self, **kwargs):
            return None

    class FakeExpense:
        expense_id = uuid4()

    class FakeExpenseResource:
        def create(self, user_id, payload, source=None, apple_wallet_transaction_id=None):
            assert user_id == 77
            assert payload.category_code == 2
            assert payload.amount == Decimal("2.90")
            assert source == "apple_wallet"
            assert apple_wallet_transaction_id == "tx-1"
            assert "MTA" in (payload.description or "")
            return FakeExpense()

    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_SECRET", "sec")
    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_USER_ID", "77")
    monkeypatch.setattr(webhook_router, "_get_expense_data_service", lambda: FakeDataService())
    monkeypatch.setattr(webhook_router, "_get_expense_resource", lambda: FakeExpenseResource())

    r = client.post(
        "/api/v1/apple-wallet/webhook",
        json={
            "merchant": "MTA OMNY",
            "amount": 2.9,
            "currency": "usd",
            "date": "2026-03-20",
            "time": "08:30",
            "transaction_id": "tx-1",
            "note": "subway",
        },
        headers={"X-Webhook-Secret": "sec"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "created"
    assert body["flow_type"] == "expense"
    assert body["category_hint"] == "expense_transport"
    assert body["expense_id"]


def test_apple_wallet_webhook_creates_income_when_classified(monkeypatch):
    class FakeDataService:
        def get_expense_by_apple_wallet_transaction_id(self, user_id, tx_id):
            return None
        def get_income_by_apple_wallet_transaction_id(self, user_id, tx_id):
            return None

        def update_apple_wallet_last_sync(self, user_id, ts):
            pass

        def get_recent_apple_wallet_expense_match(self, **kwargs):
            return None

        def get_recent_apple_wallet_income_match(self, **kwargs):
            return None

        def create_income(self, data):
            assert data["user_id"] == 88
            assert data["amount"] == Decimal("5200.00")
            assert data["income_type"] == "salary"
            assert data["date"] == date(2026, 3, 20)
            assert data["apple_wallet_transaction_id"] == "tx-2"
            return {"income_id": uuid4()}

    class FakeExpenseResource:
        def create(self, *args, **kwargs):
            raise AssertionError("Expense create should not run for income")

    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_SECRET", "sec2")
    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_USER_ID", "88")
    monkeypatch.setattr(webhook_router, "_get_expense_data_service", lambda: FakeDataService())
    monkeypatch.setattr(webhook_router, "_get_expense_resource", lambda: FakeExpenseResource())

    r = client.post(
        "/api/v1/apple-wallet/webhook",
        json={
            "merchant": "ACME Payroll",
            "amount": 5200,
            "currency": "USD",
            "date": "2026-03-20",
            "transaction_id": "tx-2",
            "note": "salary payout",
        },
        headers={"X-Webhook-Secret": "sec2"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "created"
    assert body["flow_type"] == "income"
    assert body["category_hint"] == "income_salary_other"
    assert body["income_type"] == "salary"
    assert body["income_id"]


def test_apple_wallet_webhook_income_dedup_returns_already_recorded(monkeypatch):
    existing_income_id = uuid4()

    class FakeDataService:
        def get_expense_by_apple_wallet_transaction_id(self, user_id, tx_id):
            return None

        def get_income_by_apple_wallet_transaction_id(self, user_id, tx_id):
            assert user_id == 99
            assert tx_id == "tx-income-dedup"
            return {"income_id": existing_income_id, "income_type": "salary"}

        def create_income(self, data):
            raise AssertionError("create_income should not run on dedup")

        def get_recent_apple_wallet_expense_match(self, **kwargs):
            return None

        def get_recent_apple_wallet_income_match(self, **kwargs):
            return None

    class FakeExpenseResource:
        def create(self, *args, **kwargs):
            raise AssertionError("expense create should not run on income dedup")

    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_SECRET", "sec3")
    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_USER_ID", "99")
    monkeypatch.setattr(webhook_router, "_get_expense_data_service", lambda: FakeDataService())
    monkeypatch.setattr(webhook_router, "_get_expense_resource", lambda: FakeExpenseResource())

    r = client.post(
        "/api/v1/apple-wallet/webhook",
        json={
            "merchant": "Payroll ACH",
            "amount": 3200,
            "currency": "USD",
            "date": "2026-03-20",
            "transaction_id": "tx-income-dedup",
            "note": "salary",
        },
        headers={"X-Webhook-Secret": "sec3"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "already_recorded"
    assert body["flow_type"] == "income"
    assert body["income_type"] == "salary"
    assert body["income_id"] == str(existing_income_id)


def test_apple_wallet_webhook_dedup_without_transaction_id(monkeypatch):
    existing_expense_id = uuid4()

    class FakeDataService:
        def get_recent_apple_wallet_expense_match(self, **kwargs):
            return {"expense_id": existing_expense_id}

        def get_recent_apple_wallet_income_match(self, **kwargs):
            return None

        def update_apple_wallet_last_sync(self, user_id, ts):
            pass

    class FakeExpenseResource:
        def create(self, *args, **kwargs):
            raise AssertionError("expense create should not run on heuristic dedupe")

    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_SECRET", "sec4")
    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_USER_ID", "100")
    monkeypatch.setattr(webhook_router, "_get_expense_data_service", lambda: FakeDataService())
    monkeypatch.setattr(webhook_router, "_get_expense_resource", lambda: FakeExpenseResource())

    r = client.post(
        "/api/v1/apple-wallet/webhook",
        json={
            "merchant": "Coffee Shop",
            "amount": 8.25,
            "currency": "USD",
            "date": "2026-03-20",
            "note": "latte",
        },
        headers={"X-Webhook-Secret": "sec4"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "already_recorded"
    assert body["dedupe_type"] == "heuristic_without_transaction_id"
    assert body["expense_id"] == str(existing_expense_id)


def test_apple_wallet_health_endpoint(monkeypatch):
    class FakeDataService:
        def get_apple_wallet_sync_health(self, user_id, lookback_hours):
            assert user_id == 77
            assert lookback_hours == 24
            return {
                "lookback_hours": 24,
                "window_start": datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc),
                "last_sync_at": datetime(2026, 3, 20, 11, 0, tzinfo=timezone.utc),
                "expenses_created": 4,
                "income_created": 1,
                "total_created": 5,
            }

    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_SECRET", "sec-health")
    monkeypatch.setattr(webhook_router, "APPLE_WALLET_WEBHOOK_USER_ID", "77")
    monkeypatch.setattr(webhook_router, "_get_expense_data_service", lambda: FakeDataService())

    r = client.get("/api/v1/apple-wallet/health", headers={"X-Webhook-Secret": "sec-health"})
    assert r.status_code == 200
    body = r.json()
    assert body["counters"]["total_created"] == 5
    assert body["counters"]["expenses_created"] == 4
    assert body["counters"]["income_created"] == 1
    assert body["last_sync_at"] is not None
