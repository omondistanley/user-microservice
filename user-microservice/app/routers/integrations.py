"""Integration routes: webhook ingress, digest settings, and calendar token auth."""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
import psycopg2
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from psycopg2.extras import RealDictCursor

from app.core.config import (
    APP_BASE_URL,
    APPLE_CALENDAR_CLIENT_ID,
    APPLE_CALENDAR_REDIRECT_URI,
    CALENDAR_TOKEN_BASE_URL,
    CALENDAR_OAUTH_ENABLED,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    GOOGLE_CALENDAR_CLIENT_ID,
    GOOGLE_CALENDAR_CLIENT_SECRET,
    GOOGLE_CALENDAR_REDIRECT_URI,
    INTERNAL_API_KEY,
    WEBHOOK_SIGNATURE_TOLERANCE_SECONDS,
    get_webhook_secrets,
)
from app.core.dependencies import get_current_user
from app.models.users import NotificationInternalCreate
from app.services.notification_service import create_notification

router = APIRouter()
CALENDAR_OAUTH_STATE_COOKIE = "calendar_oauth_state"
CALENDAR_OAUTH_STATE_MAX_AGE = 600


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


def _calendar_google_redirect_uri(request: Request) -> str:
    if GOOGLE_CALENDAR_REDIRECT_URI:
        return GOOGLE_CALENDAR_REDIRECT_URI
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").strip().lower()
        return f"{proto}://{forwarded_host.strip()}/api/v1/calendar/oauth/callback"
    base = (APP_BASE_URL or "").strip().rstrip("/")
    if base:
        return f"{base}/api/v1/calendar/oauth/callback"
    return f"{str(request.base_url).rstrip('/')}/api/v1/calendar/oauth/callback"


def _calendar_cookie_secure(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").strip().lower()
    return proto == "https"


def _calendar_load_connection(user_id: int) -> Optional[dict]:
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT provider, provider_account_email, provider_calendar_id, scopes,
                   token_expires_at, last_synced_at, created_at, updated_at
            FROM users_db.calendar_oauth_connection
            WHERE user_id = %s AND is_active = true
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _calendar_upsert_connection(
    user_id: int,
    provider: str,
    access_token: str,
    refresh_token: Optional[str],
    token_expires_at: Optional[datetime],
    scopes: list[str],
    provider_account_email: Optional[str],
    provider_calendar_id: Optional[str],
) -> None:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users_db.calendar_oauth_connection
                (user_id, provider, access_token, refresh_token, token_expires_at, scopes,
                 provider_account_email, provider_calendar_id, is_active, last_synced_at)
            VALUES
                (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, true, now())
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = COALESCE(EXCLUDED.refresh_token, users_db.calendar_oauth_connection.refresh_token),
                token_expires_at = EXCLUDED.token_expires_at,
                scopes = EXCLUDED.scopes,
                provider_account_email = EXCLUDED.provider_account_email,
                provider_calendar_id = EXCLUDED.provider_calendar_id,
                is_active = true,
                last_synced_at = now(),
                updated_at = now()
            """,
            (
                user_id,
                provider,
                access_token,
                refresh_token,
                token_expires_at,
                json.dumps(scopes or []),
                provider_account_email,
                provider_calendar_id,
            ),
        )
    finally:
        conn.close()


def _calendar_disconnect(user_id: int, provider: Optional[str] = None) -> int:
    conn = _get_connection()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        if provider:
            cur.execute(
                """
                UPDATE users_db.calendar_oauth_connection
                SET is_active = false, updated_at = now()
                WHERE user_id = %s AND provider = %s AND is_active = true
                """,
                (user_id, provider),
            )
        else:
            cur.execute(
                """
                UPDATE users_db.calendar_oauth_connection
                SET is_active = false, updated_at = now()
                WHERE user_id = %s AND is_active = true
                """,
                (user_id,),
            )
        return cur.rowcount or 0
    finally:
        conn.close()


@router.get("/api/v1/calendar/oauth/authorize")
async def calendar_oauth_authorize(
    request: Request,
    provider: str = Query(default="google"),
    json_response: bool = Query(default=False, alias="json"),
    current_user: dict = Depends(get_current_user),
):
    if not CALENDAR_OAUTH_ENABLED:
        raise HTTPException(status_code=503, detail="Calendar OAuth is disabled")
    user_id = int(current_user["id"])
    provider_lc = (provider or "google").strip().lower()
    if provider_lc == "apple":
        if not APPLE_CALENDAR_CLIENT_ID:
            raise HTTPException(status_code=503, detail="Apple calendar OAuth not configured")
        raise HTTPException(status_code=501, detail="Apple calendar OAuth is not yet available")
    if provider_lc != "google":
        raise HTTPException(status_code=400, detail="Unsupported calendar provider")
    if not GOOGLE_CALENDAR_CLIENT_ID or not GOOGLE_CALENDAR_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google calendar OAuth not configured")
    state = f"cal_{user_id}_{provider_lc}_{secrets.token_urlsafe(16)}"
    redirect_uri = _calendar_google_redirect_uri(request)
    params = {
        "client_id": GOOGLE_CALENDAR_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/userinfo.email",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "include_granted_scopes": "true",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    if json_response or "application/json" in (request.headers.get("accept") or "").lower():
        response = JSONResponse({"authorization_url": auth_url, "provider": provider_lc})
    else:
        response = RedirectResponse(auth_url, status_code=302)
    response.set_cookie(
        key=CALENDAR_OAUTH_STATE_COOKIE,
        value=state,
        max_age=CALENDAR_OAUTH_STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
        secure=_calendar_cookie_secure(request),
    )
    return response


@router.get("/api/v1/calendar/oauth/callback")
async def calendar_oauth_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: Optional[str] = Query(default=None),
):
    if error:
        return RedirectResponse(url="/settings/integrations?calendar=denied", status_code=302)
    cookie_state = (request.cookies.get(CALENDAR_OAUTH_STATE_COOKIE) or "").strip().strip('"')
    if not code or not state or not cookie_state or not secrets.compare_digest(cookie_state, state):
        return RedirectResponse(url="/settings/integrations?calendar=invalid_state", status_code=302)
    parts = state.split("_")
    if len(parts) < 4 or parts[0] != "cal":
        return RedirectResponse(url="/settings/integrations?calendar=invalid_state", status_code=302)
    try:
        user_id = int(parts[1])
    except ValueError:
        return RedirectResponse(url="/settings/integrations?calendar=invalid_state", status_code=302)
    provider_lc = (parts[2] or "google").lower()
    if provider_lc != "google":
        return RedirectResponse(url="/settings/integrations?calendar=provider_error", status_code=302)
    redirect_uri = _calendar_google_redirect_uri(request)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CALENDAR_CLIENT_ID,
                    "client_secret": GOOGLE_CALENDAR_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            access_token = token_data.get("access_token") or ""
            if not access_token:
                raise ValueError("Missing access token")
            refresh_token = token_data.get("refresh_token")
            expires_in = int(token_data.get("expires_in") or 0)
            token_expires_at = None
            if expires_in > 0:
                token_expires_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=expires_in)
            scope_str = token_data.get("scope") or ""
            scopes = [s for s in scope_str.split(" ") if s]
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            provider_account_email = None
            if userinfo_resp.status_code == 200:
                provider_account_email = (userinfo_resp.json().get("email") or "").strip() or None
            cal_list_resp = await client.get(
                "https://www.googleapis.com/calendar/v3/users/me/calendarList",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            provider_calendar_id = None
            if cal_list_resp.status_code == 200:
                items = cal_list_resp.json().get("items") or []
                primary = next((i for i in items if i.get("primary")), None)
                if primary:
                    provider_calendar_id = primary.get("id")
            _calendar_upsert_connection(
                user_id=user_id,
                provider="google",
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
                scopes=scopes,
                provider_account_email=provider_account_email,
                provider_calendar_id=provider_calendar_id,
            )
    except Exception:
        return RedirectResponse(url="/settings/integrations?calendar=token_error", status_code=302)
    response = RedirectResponse(url="/settings/integrations?calendar=connected", status_code=302)
    response.delete_cookie(
        key=CALENDAR_OAUTH_STATE_COOKIE,
        path="/",
        samesite="lax",
        secure=_calendar_cookie_secure(request),
    )
    return response


@router.get("/api/v1/calendar/status")
async def calendar_oauth_status(current_user: dict = Depends(get_current_user)):
    if not CALENDAR_OAUTH_ENABLED:
        return {"connected": False, "enabled": False}
    user_id = int(current_user["id"])
    row = _calendar_load_connection(user_id)
    if not row:
        return {"connected": False, "enabled": True}
    return {
        "connected": True,
        "enabled": True,
        "provider": row.get("provider"),
        "provider_account_email": row.get("provider_account_email"),
        "provider_calendar_id": row.get("provider_calendar_id"),
        "token_expires_at": row.get("token_expires_at").isoformat() if row.get("token_expires_at") else None,
        "last_synced_at": row.get("last_synced_at").isoformat() if row.get("last_synced_at") else None,
    }


@router.delete("/api/v1/calendar/disconnect")
async def calendar_oauth_disconnect(
    provider: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user["id"])
    removed = _calendar_disconnect(user_id, provider=(provider or "").strip().lower() or None)
    return {"disconnected": removed > 0, "updated": removed}


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
