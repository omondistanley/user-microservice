from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# Allow running without app installed as package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.main as main_app
import app.routers.notifications as notifications_router
import app.routers.users as users_router
from app.core.dependencies import get_current_user
from app.core.rate_limit import evaluate_rate_limit, reset_rate_limit_store
from app.main import app
from app.services.refresh_token_service import RefreshTokenValidationResult

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_rate_limits():
    reset_rate_limit_store()
    yield
    reset_rate_limit_store()


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "email": "test@example.com"}
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_refresh_reuse_writes_single_audit_event(monkeypatch):
    events = []

    def fake_validate_refresh_token(_token: str):
        return RefreshTokenValidationResult(
            status="reused",
            user_id=42,
            family_id="9a4f8f9c-6d93-4f5f-9ef2-524f5e6ed5d0",
        )

    def fake_write_audit_log(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(users_router, "validate_refresh_token", fake_validate_refresh_token)
    monkeypatch.setattr(users_router, "write_audit_log", fake_write_audit_log)

    r = client.post("/token/refresh", json={"refresh_token": "old-refresh-token"})
    assert r.status_code == 401
    assert "reuse detected" in r.json()["detail"].lower()
    assert len(events) == 1
    assert events[0]["action"] == "token_refresh_reuse_detected"
    assert events[0]["user_id"] == 42


def test_delete_account_cascade_success(auth_override, monkeypatch):
    calls = {"delete_user_account": 0, "revoke": 0}
    audit_events: list[str] = []

    async def fake_purge_business_data(user_id: int, request_id: str | None):
        assert user_id == 1
        return (
            {
                "expense": {"status": "ok", "status_code": 200},
                "budget": {"status": "ok", "status_code": 200},
            },
            [],
        )

    def fake_revoke(user_id: int):
        assert user_id == 1
        calls["revoke"] += 1
        return 1

    def fake_delete_user(user_id: int):
        assert user_id == 1
        calls["delete_user_account"] += 1
        return True

    def fake_write_audit_log(action: str, **kwargs):
        audit_events.append(action)

    monkeypatch.setattr(users_router, "_purge_business_data", fake_purge_business_data)
    monkeypatch.setattr(users_router, "revoke_all_refresh_tokens", fake_revoke)
    monkeypatch.setattr(users_router, "delete_user_account", fake_delete_user)
    monkeypatch.setattr(users_router, "write_audit_log", fake_write_audit_log)

    r = client.delete("/user/me")
    assert r.status_code == 204
    assert calls["revoke"] == 1
    assert calls["delete_user_account"] == 1
    assert "delete_account_requested" in audit_events
    assert "delete_account" in audit_events
    assert "delete_account_purge_failed" not in audit_events


def test_delete_account_cascade_partial_failure_returns_502(auth_override, monkeypatch):
    calls = {"delete_user_account": 0}
    audit_events: list[str] = []

    async def fake_purge_business_data(user_id: int, request_id: str | None):
        assert user_id == 1
        return (
            {
                "expense": {"status": "ok", "status_code": 200},
                "budget": {"status": "failed", "status_code": 500},
            },
            [
                {
                    "service": "budget",
                    "reason": "http_error",
                    "status_code": 500,
                }
            ],
        )

    def fake_delete_user(user_id: int):
        calls["delete_user_account"] += 1
        return True

    def fake_write_audit_log(action: str, **kwargs):
        audit_events.append(action)

    monkeypatch.setattr(users_router, "_purge_business_data", fake_purge_business_data)
    monkeypatch.setattr(users_router, "delete_user_account", fake_delete_user)
    monkeypatch.setattr(users_router, "revoke_all_refresh_tokens", lambda user_id: 1)
    monkeypatch.setattr(users_router, "write_audit_log", fake_write_audit_log)

    r = client.delete("/user/me")
    assert r.status_code == 502
    body = r.json()["detail"]
    assert "Failed to purge account data" in body["message"]
    assert body["rollback"] == "not_performed"
    assert calls["delete_user_account"] == 0
    assert "delete_account_requested" in audit_events
    assert "delete_account_purge_failed" in audit_events
    assert "delete_account" not in audit_events


def test_gateway_rate_limit_returns_429(auth_override, monkeypatch):
    monkeypatch.setattr(main_app, "RATE_LIMIT_API_PER_MINUTE", 1)

    def fake_list_notifications(user_id, limit=20, offset=0):
        return [], 0, 0

    monkeypatch.setattr(notifications_router, "list_notifications", fake_list_notifications)

    first = client.get("/api/v1/notifications")
    second = client.get("/api/v1/notifications")

    assert first.status_code == 200
    assert second.status_code == 429
    payload = second.json()
    assert payload["detail"] == "Rate limit exceeded"
    assert payload["scope"] == "gateway_ip"
    assert int(second.headers.get("Retry-After", "0")) >= 1


def test_rate_limit_window_resets(monkeypatch):
    now = {"value": 1000.0}

    def fake_monotonic():
        return now["value"]

    import app.core.rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module.time, "monotonic", fake_monotonic)

    decision1 = evaluate_rate_limit("window:test", max_requests=1, window_seconds=60)
    decision2 = evaluate_rate_limit("window:test", max_requests=1, window_seconds=60)

    assert decision1.allowed is True
    assert decision2.allowed is False
    assert decision2.retry_after_seconds >= 1

    now["value"] += 61.0
    decision3 = evaluate_rate_limit("window:test", max_requests=1, window_seconds=60)
    assert decision3.allowed is True
