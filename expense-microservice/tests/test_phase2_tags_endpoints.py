from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# Allow running without app installed as package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.expenses as expenses_router
import app.routers.tags as tags_router
from app.core.dependencies import get_current_user_id
from app.main import app
from app.models.expenses import ExpenseResponse

client = TestClient(app)


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user_id] = lambda: 1
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


def test_openapi_includes_tags_routes():
    spec = app.openapi()
    paths = spec.get("paths", {})
    assert "/api/v1/tags" in paths
    assert "/api/v1/tags/{tag_id}" in paths


def test_tags_crud(auth_override, monkeypatch):
    now = datetime.now(timezone.utc)
    tags: dict[str, dict] = {}

    class FakeDataService:
        def list_tags(self, user_id):
            assert user_id == 1
            return list(tags.values())

        def create_tag(self, user_id, name):
            assert user_id == 1
            if name.lower() in [t["name"].lower() for t in tags.values()]:
                raise PermissionError("Tag already exists")
            tag_id = str(uuid4())
            row = {
                "tag_id": tag_id,
                "user_id": 1,
                "name": name,
                "slug": name.lower(),
                "created_at": now,
                "updated_at": now,
            }
            tags[tag_id] = row
            return row

        def delete_tag(self, user_id, tag_id):
            assert user_id == 1
            return tags.pop(tag_id, None) is not None

    monkeypatch.setattr(tags_router, "_get_data_service", lambda: FakeDataService())

    r = client.post("/api/v1/tags", json={"name": "Groceries"})
    assert r.status_code == 200
    body = r.json()
    created_tag_id = body["tag_id"]
    assert body["name"] == "Groceries"
    assert body["slug"] == "groceries"

    r = client.get("/api/v1/tags")
    assert r.status_code == 200
    tags_payload = r.json()
    assert len(tags_payload) == 1
    assert tags_payload[0]["tag_id"] == created_tag_id

    r = client.post("/api/v1/tags", json={"name": "groceries"})
    assert r.status_code == 409

    r = client.delete(f"/api/v1/tags/{created_tag_id}")
    assert r.status_code == 204

    r = client.get("/api/v1/tags")
    assert r.status_code == 200
    assert r.json() == []


def test_expense_list_filters_by_tag(auth_override, monkeypatch):
    now = datetime.now(timezone.utc)
    expense_id = uuid4()
    tag_id = uuid4()

    class FakeExpenseResource:
        def list(self, user_id, params):
            assert user_id == 1
            assert params.tag == "groceries"
            assert params.tag_id is None
            return [
                ExpenseResponse(
                    expense_id=expense_id,
                    user_id=1,
                    category_code=1,
                    category_name="Food",
                    amount=Decimal("42.50"),
                    date=date(2026, 2, 27),
                    currency="USD",
                    description="Store",
                    balance_after=Decimal("300.00"),
                    created_at=now,
                    updated_at=now,
                    source="manual",
                    plaid_transaction_id=None,
                    tags=[
                        {
                            "tag_id": tag_id,
                            "user_id": 1,
                            "name": "Groceries",
                            "slug": "groceries",
                            "created_at": now,
                            "updated_at": now,
                        }
                    ],
                )
            ], 1

    monkeypatch.setattr(expenses_router, "_get_expense_resource", lambda: FakeExpenseResource())
    r = client.get("/api/v1/expenses?tag=groceries")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["tags"][0]["slug"] == "groceries"
