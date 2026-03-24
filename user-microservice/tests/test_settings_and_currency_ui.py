from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

# Allow running without app installed as package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.settings as settings_router
from app.core.dependencies import get_current_user
from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "email": "test@example.com"}
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_settings_api_get_and_patch(auth_override, monkeypatch):
    now = datetime.now(timezone.utc)
    store = {"user_id": 1, "default_currency": "USD", "updated_at": now}

    def fake_get(user_id):
        assert user_id == 1
        return dict(store)

    def fake_update(user_id, default_currency):
        assert user_id == 1
        store["default_currency"] = str(default_currency).upper()
        return dict(store)

    monkeypatch.setattr(settings_router, "get_user_settings", fake_get)
    monkeypatch.setattr(settings_router, "update_default_currency", fake_update)

    r = client.get("/api/v1/settings")
    assert r.status_code == 200
    assert r.json()["default_currency"] == "USD"

    r = client.patch("/api/v1/settings", json={"default_currency": "eur"})
    assert r.status_code == 200
    assert r.json()["default_currency"] == "EUR"


def test_currency_selector_present_on_dashboard_and_reports():
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "dashboard-savings-rate" in r.text

    r = client.get("/reports")
    assert r.status_code == 200
    assert "reports-currency" in r.text
