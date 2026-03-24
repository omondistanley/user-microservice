"""
Sprint 4 — Gmail OAuth2 authorisation flow + Pub/Sub receipt webhook.

Endpoints:
  GET  /api/v1/gmail/oauth/authorize  — redirect user to Google consent screen
  GET  /api/v1/gmail/oauth/callback   — exchange auth code, store token, start watch
  POST /api/v1/gmail/webhook          — Pub/Sub push notification handler
  GET  /api/v1/gmail/status           — show OAuth status for current user

All endpoints except /webhook require a valid JWT (get_current_user_id).
The /webhook endpoint is authenticated by the Pub/Sub push URL secret token
configured at subscription creation time (GCP enforces HTTPS + JWT validation
natively; we verify the `token` query param set when the subscription was created).
"""
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.core.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
from app.core.dependencies import get_current_user_id
from app.services.gmail_receipt_service import (
    decode_gmail_pubsub_data,
    delete_gmail_oauth_for_user,
    exchange_code_for_tokens,
    fetch_gmail_profile_email,
    get_authorization_url,
    is_configured,
    load_oauth_token,
    process_pubsub_notification,
    register_gmail_watch,
    resolve_user_id_by_google_email,
    save_oauth_token,
)

logger = logging.getLogger("gmail_webhook_router")
router = APIRouter(prefix="/api/v1/gmail", tags=["gmail"])

_PUBSUB_TOKEN_ENV = "GMAIL_PUBSUB_VERIFICATION_TOKEN"


def _db_context() -> Dict[str, Any]:
    return {
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "dbname": DB_NAME or "expenses_db",
    }


def _require_configured():
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Gmail integration not configured. "
                "Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, and GMAIL_REDIRECT_URI."
            ),
        )


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

@router.get("/oauth/authorize")
async def gmail_oauth_authorize(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    json: bool = Query(default=False, description="If true, return JSON with authorization_url (for SPA/fetch clients)"),
):
    """
    Redirect the authenticated user to Google's OAuth2 consent screen.
    After consent, Google redirects to /gmail/oauth/callback.

    Use ?json=1 or Accept: application/json to receive {"authorization_url": "..."} so the browser
    can navigate with Authorization headers from prior fetch.
    """
    _require_configured()
    state = f"uid_{user_id}"
    auth_url = get_authorization_url(state=state)
    accept = (request.headers.get("accept") or "").lower()
    if json or "application/json" in accept:
        return JSONResponse({"authorization_url": auth_url})
    return RedirectResponse(url=auth_url)


@router.get("/oauth/callback")
async def gmail_oauth_callback(
    code: str = Query(...),
    state: str = Query(default=""),
    error: Optional[str] = Query(default=None),
):
    """
    Google OAuth2 callback. Exchanges the auth code for tokens, saves them,
    and registers a Pub/Sub watch on the user's inbox.
    """
    _require_configured()
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    # Decode user_id from state
    user_id: Optional[int] = None
    if state.startswith("uid_"):
        try:
            user_id = int(state[4:])
        except ValueError:
            pass
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid OAuth state parameter")

    try:
        token_data = exchange_code_for_tokens(code)
    except Exception as exc:
        logger.error("gmail_oauth_exchange_failed user_id=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {exc}")

    profile_email = fetch_gmail_profile_email(token_data.get("access_token") or "")
    ctx = _db_context()
    save_oauth_token(ctx, user_id, token_data, google_account_email=profile_email)
    logger.info(
        "gmail_oauth_token_saved user_id=%s email=%s",
        user_id,
        profile_email or "?",
    )

    # Best-effort watch registration
    watch_result: Dict[str, Any] = {}
    try:
        watch_result = register_gmail_watch(ctx, user_id)
    except Exception as exc:
        logger.warning("gmail_watch_register_failed user_id=%s: %s", user_id, exc)

    success_redirect = os.environ.get("GMAIL_OAUTH_SUCCESS_REDIRECT", "").strip()
    if success_redirect:
        sep = "&" if "?" in success_redirect else "?"
        return RedirectResponse(
            url=f"{success_redirect}{sep}gmail=connected",
            status_code=302,
        )

    return {
        "status": "connected",
        "user_id": user_id,
        "scopes": token_data.get("scopes", []),
        "watch": watch_result,
        "message": (
            "Gmail connected. New receipt emails will be captured automatically. "
            "If Pub/Sub watch failed, re-trigger via POST /gmail/watch."
        ),
    }


@router.post("/watch")
async def register_watch(
    user_id: int = Depends(get_current_user_id),
):
    """
    (Re-)register the Gmail Pub/Sub watch for the current user.
    Call this if the watch has expired (watches last ~7 days; renew weekly).
    """
    _require_configured()
    ctx = _db_context()
    try:
        result = register_gmail_watch(ctx, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("gmail_watch_failed user_id=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "watch_registered", "result": result}


# ---------------------------------------------------------------------------
# Pub/Sub push webhook
# ---------------------------------------------------------------------------

class PubSubMessage(BaseModel):
    data: str           # base64-encoded JSON  {"emailAddress": "...", "historyId": 123}
    messageId: Optional[str] = None
    publishTime: Optional[str] = None
    attributes: Optional[Dict[str, str]] = None


class PubSubPushPayload(BaseModel):
    message: PubSubMessage
    subscription: Optional[str] = None


@router.post("/webhook")
async def gmail_pubsub_webhook(
    body: PubSubPushPayload,
    token: Optional[str] = Query(default=None, description="Pub/Sub push verification token"),
):
    """
    Receives Pub/Sub push notifications when new Gmail messages arrive.

    Authentication: GCP push subscriptions should be configured with a
    verification token (appended as ?token=<secret> in the push URL).
    Set GMAIL_PUBSUB_VERIFICATION_TOKEN to enforce it.
    """
    expected_token = os.environ.get(_PUBSUB_TOKEN_ENV, "").strip()
    if expected_token and token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid Pub/Sub verification token")

    notification = decode_gmail_pubsub_data(body.message.data)
    push_email = (notification.get("emailAddress") or "").strip()
    ctx = _db_context()
    user_id = resolve_user_id_by_google_email(ctx, push_email) if push_email else None

    if user_id is None:
        legacy = (
            os.environ.get("GMAIL_WEBHOOK_LEGACY_USER_ID", "").strip()
            or os.environ.get("APPLE_WALLET_WEBHOOK_USER_ID", "").strip()
        )
        if legacy:
            try:
                user_id = int(legacy)
            except ValueError:
                user_id = None

    if user_id is None:
        logger.warning(
            "gmail_webhook_no_user_for_email email=%s (set GMAIL_WEBHOOK_LEGACY_USER_ID for single-tenant dev)",
            push_email or "(empty)",
        )
        return {"status": "ack", "processed": 0}

    results = process_pubsub_notification(ctx, user_id, body.message.data)
    created = sum(1 for r in results if r.get("status") == "created")
    logger.info("gmail_webhook_processed user_id=%s total=%s created=%s", user_id, len(results), created)
    return {"status": "ack", "processed": len(results), "created": created}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def gmail_status(
    user_id: int = Depends(get_current_user_id),
):
    """Return whether Gmail is connected and watch metadata for current user."""
    _require_configured()
    ctx = _db_context()
    token_data = load_oauth_token(ctx, user_id)
    if not token_data:
        return {"connected": False, "user_id": user_id}
    return {
        "connected": True,
        "user_id": user_id,
        "scopes": token_data.get("scopes", []),
        "google_account_email": token_data.get("_google_account_email"),
        "history_id": token_data.get("_history_id"),
        "watch_expiry": str(token_data.get("_watch_expiry")) if token_data.get("_watch_expiry") else None,
    }


@router.delete("/disconnect")
async def gmail_disconnect(user_id: int = Depends(get_current_user_id)):
    """Remove stored Gmail OAuth tokens and receipt processing log for the current user."""
    ctx = _db_context()
    n = delete_gmail_oauth_for_user(ctx, user_id)
    return {"status": "disconnected", "removed": n > 0}
