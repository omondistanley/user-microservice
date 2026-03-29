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
    store = {
        "user_id": 1,
        "default_currency": "USD",
        "theme_preference": "system",
        "push_notifications_enabled": True,
        "email_notifications_enabled": False,
        "updated_at": now,
        "active_household_id": None,
    }

    def fake_get(user_id):
        assert user_id == 1
        return dict(store)

    def fake_update(user_id, **kwargs):
        assert user_id == 1
        for key, value in kwargs.items():
            if value is not None:
                store[key] = str(value).upper() if key == "default_currency" else value
        return dict(store)

    monkeypatch.setattr(settings_router, "get_user_settings", fake_get)
    monkeypatch.setattr(settings_router, "update_user_settings", fake_update)

    r = client.get("/api/v1/settings")
    assert r.status_code == 200
    assert r.json()["default_currency"] == "USD"
    assert r.json()["theme_preference"] == "system"

    r = client.patch(
        "/api/v1/settings",
        json={
            "default_currency": "eur",
            "theme_preference": "dark",
            "push_notifications_enabled": False,
            "email_notifications_enabled": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["default_currency"] == "EUR"
    assert r.json()["theme_preference"] == "dark"
    assert r.json()["push_notifications_enabled"] is False
    assert r.json()["email_notifications_enabled"] is True


def test_currency_selector_present_on_dashboard_and_reports():
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "dashboard-savings-rate" in r.text

    r = client.get("/reports")
    assert r.status_code == 200
    assert "reports-currency" in r.text
