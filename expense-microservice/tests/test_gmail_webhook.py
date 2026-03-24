"""Gmail Pub/Sub webhook and helpers."""
import base64
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.services import gmail_receipt_service as grs

client = TestClient(app)


def test_decode_gmail_pubsub_data_roundtrip():
    inner = {"emailAddress": "user@example.com", "historyId": 12345}
    b64 = base64.b64encode(json.dumps(inner).encode()).decode()
    out = grs.decode_gmail_pubsub_data(b64)
    assert out["emailAddress"] == "user@example.com"
    assert out["historyId"] == 12345


def test_gmail_webhook_rejects_bad_verification_token(monkeypatch):
    monkeypatch.setenv("GMAIL_PUBSUB_VERIFICATION_TOKEN", "expected-secret")
    payload = {"emailAddress": "a@b.com", "historyId": 1}
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    r = client.post(
        "/api/v1/gmail/webhook?token=wrong",
        json={"message": {"data": b64}},
    )
    assert r.status_code == 401


def test_gmail_webhook_processes_for_resolved_user(monkeypatch):
    monkeypatch.delenv("GMAIL_PUBSUB_VERIFICATION_TOKEN", raising=False)
    payload = {"emailAddress": "shopper@example.com", "historyId": 999}
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()

    calls = []

    def fake_resolve(ctx, email):
        calls.append(email)
        return 7 if email == "shopper@example.com" else None

    def fake_process(ctx, user_id, encoded):
        assert user_id == 7
        assert encoded == b64
        return [{"message_id": "m1", "status": "created"}]

    import app.routers.gmail_webhook as gw

    monkeypatch.setattr(gw, "resolve_user_id_by_google_email", fake_resolve)
    monkeypatch.setattr(gw, "process_pubsub_notification", fake_process)

    r = client.post("/api/v1/gmail/webhook", json={"message": {"data": b64}})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ack"
    assert body["processed"] == 1
    assert body["created"] == 1
    assert calls == ["shopper@example.com"]


def test_gmail_webhook_legacy_user_when_unmapped(monkeypatch):
    monkeypatch.delenv("GMAIL_PUBSUB_VERIFICATION_TOKEN", raising=False)
    monkeypatch.setenv("GMAIL_WEBHOOK_LEGACY_USER_ID", "99")
    payload = {"emailAddress": "unknown@example.com", "historyId": 1}
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()

    import app.routers.gmail_webhook as gw

    monkeypatch.setattr(gw, "resolve_user_id_by_google_email", lambda ctx, e: None)

    def fake_process(ctx, user_id, encoded):
        assert user_id == 99
        return []

    monkeypatch.setattr(gw, "process_pubsub_notification", fake_process)
    r = client.post("/api/v1/gmail/webhook", json={"message": {"data": b64}})
    assert r.status_code == 200
