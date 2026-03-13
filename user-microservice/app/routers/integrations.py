"""Integration routes: webhook ingress, digest settings, and calendar token auth."""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from psycopg2.extras import RealDictCursor

from app.core.config import (
    CALENDAR_TOKEN_BASE_URL,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    INTERNAL_API_KEY,
    WEBHOOK_SIGNATURE_TOLERANCE_SECONDS,
    get_webhook_secrets,
)
from app.core.dependencies import get_current_user
from app.models.users import NotificationInternalCreate
from app.services.notification_service import create_notification

router = APIRouter()


def _get_connection():
    return psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )


def _validate_internal_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    if INTERNAL_API_KEY and x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def _validate_signature(
    provider: str,
    payload: bytes,
    signature: Optional[str],
    ts_header: Optional[str],
) -> bool:
    """Validate HMAC signature and optional timestamp window."""
    secret = get_webhook_secrets().get((provider or "").lower())
    if not secret:
        # dev fallback if no secret configured
        return True
    if not signature:
        return False
    if ts_header:
        try:
            ts = int(ts_header)
            now_ts = int(datetime.now(timezone.utc).timestamp())
            if abs(now_ts - ts) > WEBHOOK_SIGNATURE_TOLERANCE_SECONDS:
                return False
        except ValueError:
            return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    incoming = signature
    if incoming.startswith("sha256="):
        incoming = incoming[7:]
    return hmac.compare_digest(expected, incoming)


class DigestConfigUpdate(BaseModel):
    frequency: str = Field("weekly", pattern="^(weekly|monthly)$")
    channel: str = Field("email", pattern="^(email|slack_webhook)$")
    channel_target: Optional[str] = None
    is_active: bool = True


@router.post("/api/v1/integrations/webhooks/{provider}")
async def webhook_ingest(
    provider: str,
    request: Request,
    x_webhook_signature: Optional[str] = Header(None),
    x_webhook_timestamp: Optional[str] = Header(None),
):
    """Accept webhook payload; validate signature; store for idempotency and async processing."""
    body = await request.body()
    if not _validate_signature(provider, body, x_webhook_signature, x_webhook_timestamp):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        data = json.loads(body)
    except Exception:
        data = None
    event_id = (data.get("id") or data.get("event_id") or request.headers.get("x-request-id")) if isinstance(data, dict) else request.headers.get("x-request-id")
    if not event_id:
        event_id = hashlib.sha256(body).hexdigest()[:64]
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users_db.webhook_event
                (provider, event_id, payload_json, status, attempt_count, next_retry_at, headers_json, received_at)
            VALUES
                (%s, %s, %s::jsonb, 'pending', 0, now(), %s::jsonb, now())
            ON CONFLICT (provider, event_id) DO NOTHING
            """,
            (
                provider[:64],
                str(event_id)[:255],
                json.dumps(data) if data is not None else None,
                json.dumps({k.lower(): v for k, v in request.headers.items()}),
            ),
        )
        if cur.rowcount == 0:
            return {"status": "duplicate", "event_id": event_id}
        return {"status": "accepted", "event_id": event_id}
    finally:
        conn.close()


@router.get("/api/v1/integrations/digest-config")
async def get_digest_config(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, frequency, channel, channel_target, is_active, last_sent_at, updated_at
            FROM users_db.digest_config
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"configured": False}
        return {"configured": True, **dict(row)}
    finally:
        conn.close()


@router.put("/api/v1/integrations/digest-config")
async def upsert_digest_config(payload: DigestConfigUpdate, current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users_db.digest_config (user_id, frequency, channel, channel_target, is_active, updated_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (user_id, channel)
            DO UPDATE SET
                frequency = EXCLUDED.frequency,
                channel_target = EXCLUDED.channel_target,
                is_active = EXCLUDED.is_active,
                updated_at = now()
            RETURNING id, user_id, frequency, channel, channel_target, is_active, last_sent_at, updated_at
            """,
            (
                user_id,
                payload.frequency,
                payload.channel,
                payload.channel_target,
                payload.is_active,
            ),
        )
        row = cur.fetchone()
        return dict(row) if row else {"ok": True}
    finally:
        conn.close()


@router.post("/api/v1/integrations/digest-test")
async def send_digest_test(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    note = create_notification(
        user_id=user_id,
        notification_type="digest_test",
        title="Digest test queued",
        body="Digest configuration saved. The scheduled worker will deliver future digests.",
        payload={"source": "integrations"},
    )
    return {"ok": True, "notification_id": str(note.get("notification_id")) if note else None}


def _hash_calendar_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/api/v1/integrations/calendar/token")
async def rotate_calendar_token(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_calendar_token(raw_token)
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users_db.calendar_subscription_token
            SET is_active = false, revoked_at = now()
            WHERE user_id = %s AND is_active = true
            """,
            (user_id,),
        )
        cur.execute(
            """
            INSERT INTO users_db.calendar_subscription_token (user_id, token_hash, is_active)
            VALUES (%s, %s, true)
            """,
            (user_id, token_hash),
        )
    finally:
        conn.close()
    calendar_url = f"{CALENDAR_TOKEN_BASE_URL}/api/v1/reminders/calendar.ics?token={raw_token}&days_ahead=90"
    return {"token": raw_token, "calendar_url": calendar_url}


@router.get("/api/v1/integrations/calendar/token")
async def get_calendar_token_status(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at
            FROM users_db.calendar_subscription_token
            WHERE user_id = %s AND is_active = true
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return {"has_active_token": bool(row), "created_at": row.get("created_at") if row else None}
    finally:
        conn.close()


@router.delete("/api/v1/integrations/calendar/token")
async def revoke_calendar_token(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users_db.calendar_subscription_token
            SET is_active = false, revoked_at = now()
            WHERE user_id = %s AND is_active = true
            """,
            (user_id,),
        )
        return {"revoked": cur.rowcount or 0}
    finally:
        conn.close()


@router.get("/internal/v1/calendar/subscription/{token}", include_in_schema=False)
async def validate_calendar_subscription(
    token: str,
    _: None = Depends(_validate_internal_key),
):
    token_hash = _hash_calendar_token(token)
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id
            FROM users_db.calendar_subscription_token
            WHERE token_hash = %s AND is_active = true
            LIMIT 1
            """,
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subscription token not found")
        return {"user_id": int(row["user_id"])}
    finally:
        conn.close()


@router.post("/internal/v1/notifications", include_in_schema=False)
async def create_internal_notification(
    payload: NotificationInternalCreate,
    _: None = Depends(_validate_internal_key),
):
    row = create_notification(
        user_id=payload.user_id,
        notification_type=payload.type,
        title=payload.title,
        body=payload.body,
        payload=payload.payload,
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create notification")
    return row
