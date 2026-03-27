from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.users as users_router
from app.core.dependencies import get_current_user
from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "email": "test@example.com"}
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_forgot_password_routes_share_contract(monkeypatch):
    calls: list[str] = []

    def fake_create_reset_token(email: str):
        calls.append(email)

    monkeypatch.setattr(users_router, "create_reset_token", fake_create_reset_token)

    canonical = client.post("/forgot-password", json={"email": "test@example.com"})
    legacy = client.post("/api/v1/users/forgot-password", json={"email": "test@example.com"})

    assert canonical.status_code == 200
    assert legacy.status_code == 200
    assert canonical.json() == legacy.json()
    assert calls == ["test@example.com", "test@example.com"]


def test_reset_password_routes_share_contract(monkeypatch):
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(users_router, "validate_and_consume_reset_token", lambda token: 7 if token == "ok" else None)
    monkeypatch.setattr(users_router, "set_password", lambda user_id, password: events.append(("set", user_id, password)))
    monkeypatch.setattr(users_router, "revoke_all_refresh_tokens", lambda user_id: events.append(("revoke", user_id)))
    monkeypatch.setattr(users_router, "write_audit_log", lambda **kwargs: events.append(("audit", kwargs["user_id"])))

    canonical = client.post("/reset-password", json={"token": "ok", "new_password": "BetterPass123!"})
    legacy = client.post("/api/v1/users/reset-password", json={"token": "ok", "new_password": "BetterPass123!"})

    assert canonical.status_code == 200
    assert legacy.status_code == 200
    assert canonical.json()["message"] == legacy.json()["message"]
    assert ("set", 7, "BetterPass123!") in events
    assert ("revoke", 7) in events


def test_get_and_patch_me_return_mobile_and_web_profile_fields(auth_override, monkeypatch):
    now = datetime.now(timezone.utc)
    row = {
        "id": 1,
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "bio": "Initial bio",
        "created_at": now,
        "email_verified_at": now,
        "auth_provider": "password",
    }

    class FakeDataService:
        def get_data_object(self, *_args, **kwargs):
            return dict(row)

        def update_data_object(self, _database, _collection, _user_id, updates):
            row.update(updates)

    fake_service = FakeDataService()
    monkeypatch.setattr(
        users_router.ServiceFactory,
        "get_service",
        lambda name: fake_service if name == "UserResourceDataService" else None,
    )

    got = client.get("/user/me")
    assert got.status_code == 200
    body = got.json()
    assert body["bio"] == "Initial bio"
    assert body["auth_provider"] == "password"
    assert body["email_verified_at"] is not None
    assert body["created_at"] is not None

    patched = client.patch("/user/me", json={"first_name": "  Casey ", "bio": "  Updated bio  "})
    assert patched.status_code == 200
    patched_body = patched.json()
    assert patched_body["first_name"] == "Casey"
    assert patched_body["bio"] == "Updated bio"
    assert patched_body["email_verified_at"] is not None


def test_savings_goals_alias_redirects_to_goals():
    r = client.get("/savings-goals", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/goals"
