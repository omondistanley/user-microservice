"""
Test that Plaid and Teller endpoints return 503 when not configured.
"""
import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.dependencies import get_current_user_id
from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user_id] = lambda: 1
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


def test_plaid_status_503_when_not_configured(auth_override, monkeypatch):
    """GET /api/v1/plaid/status returns 503 when Plaid env is not set."""
    import app.services.plaid_service as plaid_service
    monkeypatch.setattr(plaid_service, "is_configured", lambda: False)
    r = client.get("/api/v1/plaid/status", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 503
    body = r.json()
    assert "not configured" in body.get("detail", "").lower()


def test_plaid_link_token_503_when_not_configured(auth_override, monkeypatch):
    """POST /api/v1/plaid/link-token returns 503 when Plaid is not configured."""
    import app.services.plaid_service as plaid_service
    monkeypatch.setattr(plaid_service, "is_configured", lambda: False)
    r = client.post(
        "/api/v1/plaid/link-token",
        headers={"Authorization": "Bearer fake"},
    )
    assert r.status_code == 503
    body = r.json()
    assert "not configured" in body.get("detail", "").lower()


def test_plaid_exchange_503_when_not_configured(auth_override, monkeypatch):
    """POST /api/v1/plaid/item returns 503 when Plaid is not configured."""
    import app.services.plaid_service as plaid_service
    monkeypatch.setattr(plaid_service, "is_configured", lambda: False)
    r = client.post(
        "/api/v1/plaid/item",
        json={"public_token": "fake-token"},
        headers={"Authorization": "Bearer fake"},
    )
    assert r.status_code == 503
    body = r.json()
    assert "not configured" in body.get("detail", "").lower()


def test_teller_config_503_when_not_configured(monkeypatch):
    """GET /api/v1/teller/config returns 503 when Teller is not configured (no auth required)."""
    import app.core.config as config
    monkeypatch.setattr(config, "TELLER_APP_ID", "")
    r = client.get("/api/v1/teller/config")
    assert r.status_code == 503
    body = r.json()
    assert "not configured" in body.get("detail", "").lower()


def test_truelayer_status_503_when_not_configured(monkeypatch):
    """GET /api/v1/truelayer/status returns 503 when TrueLayer is not configured."""
    import app.adapters.truelayer_adapter as truelayer_adapter
    monkeypatch.setattr(truelayer_adapter, "is_configured", lambda: False)
    r = client.get("/api/v1/truelayer/status")
    assert r.status_code == 503
    body = r.json()
    assert "not configured" in body.get("detail", "").lower()
