from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import sys
from pathlib import Path

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.expenses import ExpenseCreate
from app.resources.expense_resource import ExpenseResource
from app.services.expense_data_service import ExpenseDataService
from app.services.field_encryption import encrypt_field
from app.services import rule_engine_service


class _ListCursor:
    def __init__(self, rows):
        self.rows = rows
        self._mode = None

    def execute(self, sql, params):
        self._mode = "count" if "COUNT(*)" in sql else "list"

    def fetchone(self):
        if self._mode == "count":
            return {"c": len(self.rows)}
        return None

    def fetchall(self):
        if self._mode == "list":
            return self.rows
        return []


class _ListConn:
    def __init__(self, rows):
        self._cursor = _ListCursor(rows)

    def cursor(self):
        return self._cursor

    def close(self):
        pass


class _ListExpenseDataService(ExpenseDataService):
    def __init__(self, rows):
        self._rows = rows

    def _conn_autocommit(self):  # type: ignore[override]
        return _ListConn(self._rows)


class _CreateConn:
    def cursor(self):
        return object()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _CreateExpenseDataService:
    def __init__(self, created_at):
        self.created_at = created_at
        self.created_expense_id = None
        self.get_by_id_calls = 0

    def resolve_category(self, category_code, category):
        return 1, "Food"

    def get_connection(self, autocommit=True):
        return _CreateConn()

    def acquire_user_lock(self, conn, user_id):
        return None

    def _insert_expense_using_conn(self, conn, data):
        self.created_expense_id = uuid4()
        data["expense_id"] = self.created_expense_id
        data["created_at"] = self.created_at
        data["updated_at"] = self.created_at
        data["description"] = encrypt_field(data["description"])
        return data

    def set_expense_tags(self, **kwargs):
        return []

    def get_previous_expense(self, user_id, date_val, created_at, expense_id, conn=None):
        return None

    def update_expense_balance_after(self, conn, expense_id, user_id, balance_after):
        return None

    def recalc_balance_after(self, conn, user_id, pivot_date, pivot_created_at, pivot_expense_id, balance_before_pivot):
        return None

    def get_expense_by_id(self, expense_id, user_id):
        self.get_by_id_calls += 1
        assert expense_id == self.created_expense_id
        return {
            "expense_id": expense_id,
            "user_id": user_id,
            "category_code": 1,
            "category_name": "Food",
            "amount": Decimal("12.34"),
            "date": date(2026, 3, 27),
            "currency": "USD",
            "budget_category_id": None,
            "description": "Gateway E2E coffee",
            "balance_after": Decimal("-12.34"),
            "created_at": self.created_at,
            "updated_at": self.created_at,
            "source": None,
            "plaid_transaction_id": None,
            "apple_wallet_transaction_id": None,
        }

    def get_tags_for_expense(self, expense_id, user_id):
        return []


def test_list_expenses_decrypts_description(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    now = datetime.now(timezone.utc)
    encrypted_description = encrypt_field("Gateway E2E coffee")
    service = _ListExpenseDataService(
        [
            {
                "expense_id": uuid4(),
                "user_id": 1,
                "category_code": 1,
                "category_name": "Food",
                "amount": Decimal("12.34"),
                "date": date(2026, 3, 27),
                "currency": "USD",
                "budget_category_id": None,
                "description": encrypted_description,
                "balance_after": Decimal("-12.34"),
                "created_at": now,
                "updated_at": now,
                "source": None,
                "plaid_transaction_id": None,
                "apple_wallet_transaction_id": None,
            }
        ]
    )

    rows, total = service.list_expenses(user_id=1, limit=20, offset=0)

    assert total == 1
    assert rows[0]["description"] == "Gateway E2E coffee"


def test_create_expense_returns_decrypted_description(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(rule_engine_service, "evaluate_rules", lambda *args, **kwargs: None)
    now = datetime.now(timezone.utc)
    resource = ExpenseResource({})
    resource.data_service = _CreateExpenseDataService(now)

    response = resource.create(
        user_id=1,
        payload=ExpenseCreate(
            amount=Decimal("12.34"),
            category_code=1,
            date=date(2026, 3, 27),
            currency="USD",
            description="Gateway E2E coffee",
        ),
    )

    assert response.description == "Gateway E2E coffee"
    assert resource.data_service.get_by_id_calls == 1
