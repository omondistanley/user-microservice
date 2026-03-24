import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.integrations as integrations_router
from app.core.dependencies import get_current_user
from app.main import app

client = TestClient(app)


def _auth_user():
    return {"id": 7, "email": "user@example.com"}


def test_calendar_status_and_disconnect(monkeypatch):
    app.dependency_overrides[get_current_user] = _auth_user
    monkeypatch.setattr(
        integrations_router,
        "_calendar_load_connection",
        lambda user_id: {
            "provider": "google",
            "provider_account_email": "user@example.com",
            "provider_calendar_id": "primary",
            "token_expires_at": None,
            "last_synced_at": None,
        },
    )
    monkeypatch.setattr(integrations_router, "_calendar_disconnect", lambda user_id, provider=None: 1)
    try:
        r = client.get("/api/v1/calendar/status")
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is True
        assert data["provider"] == "google"

        r = client.delete("/api/v1/calendar/disconnect?provider=google")
        assert r.status_code == 200
        assert r.json()["disconnected"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_calendar_authorize_json(monkeypatch):
    app.dependency_overrides[get_current_user] = _auth_user
    monkeypatch.setattr(integrations_router, "GOOGLE_CALENDAR_CLIENT_ID", "abc")
    monkeypatch.setattr(integrations_router, "GOOGLE_CALENDAR_CLIENT_SECRET", "def")
    try:
        r = client.get("/api/v1/calendar/oauth/authorize?provider=google&json=1")
        assert r.status_code == 200
        payload = r.json()
        assert payload["provider"] == "google"
        assert "authorization_url" in payload
        assert "accounts.google.com" in payload["authorization_url"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_integrations_page_hides_non_core_sections():
    r = client.get("/settings/integrations")
    assert r.status_code == 200
    body = r.text
    assert "Bank Accounts" in body
    assert "Alpaca Brokerage" in body
    assert "Gmail receipts" not in body
    assert "Digest" not in body
    assert "Calendar Reminders" not in body
    assert "Data Export" not in body
