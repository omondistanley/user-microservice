from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# Allow running without app installed as package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.notifications as notifications_router
from app.core.dependencies import get_current_user
from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_override():
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "email": "test@example.com"}
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_notifications_require_auth():
    r = client.get("/api/v1/notifications")
    assert r.status_code == 401


def test_openapi_includes_notification_paths():
    spec = app.openapi()
    paths = spec.get("paths", {})
    assert "/api/v1/notifications" in paths
    assert "/api/v1/notifications/{notification_id}/read" in paths
    assert "/api/v1/notifications/read-all" in paths


def test_notification_read_endpoints_are_idempotent(auth_override, monkeypatch):
    notification_id = str(uuid4())
    now = datetime.now(timezone.utc)
    store = {
        notification_id: {
            "notification_id": notification_id,
            "user_id": 1,
            "type": "budget_alert",
            "title": "Budget threshold reached",
            "body": "Spent reached 80%",
            "is_read": False,
            "payload_json": {"budget_id": "abc"},
            "created_at": now,
            "read_at": None,
        }
    }

    def fake_list_notifications(user_id, limit=20, offset=0):
        assert user_id == 1
        items = list(store.values())
        unread = len([x for x in items if not x["is_read"]])
        return items, len(items), unread

    def fake_mark_notification_read(user_id, notification_id):
        assert user_id == 1
        row = store.get(notification_id)
        if not row:
            return None
        if not row["is_read"]:
            row["is_read"] = True
            row["read_at"] = now
        return row

    def fake_mark_all_notifications_read(user_id):
        assert user_id == 1
        updated = 0
        for row in store.values():
            if not row["is_read"]:
                row["is_read"] = True
                row["read_at"] = now
                updated += 1
        return updated

    monkeypatch.setattr(notifications_router, "list_notifications", fake_list_notifications)
    monkeypatch.setattr(notifications_router, "mark_notification_read", fake_mark_notification_read)
    monkeypatch.setattr(notifications_router, "mark_all_notifications_read", fake_mark_all_notifications_read)

    r = client.get("/api/v1/notifications")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["unread"] == 1

    r = client.patch(f"/api/v1/notifications/{notification_id}/read")
    assert r.status_code == 200
    assert r.json()["is_read"] is True

    r = client.patch(f"/api/v1/notifications/{notification_id}/read")
    assert r.status_code == 200
    assert r.json()["is_read"] is True

    r = client.patch("/api/v1/notifications/read-all")
    assert r.status_code == 200
    assert r.json()["updated"] == 0

    r = client.get("/api/v1/notifications")
    assert r.status_code == 200
    assert r.json()["unread"] == 0
