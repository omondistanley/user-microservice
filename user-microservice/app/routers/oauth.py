"""
OAuth 2.0 routes for Google and Apple sign-in.
Redirect to provider, then callback finds or creates user and issues JWT; redirect to app with tokens in fragment.
"""
import hashlib
import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import httpx

from app.core.config import (
    APP_BASE_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    APPLE_CLIENT_ID,
    APPLE_REDIRECT_URI,
)
from app.core.security import create_access_token
from app.services.refresh_token_service import create_refresh_token
from app.services.session_service import create_session
from app.services.audit_log_service import write_audit_log
from app.services.service_factory import ServiceFactory

router = APIRouter()
logger = logging.getLogger(__name__)

OAUTH_STATE_COOKIE = "oauth_state"
OAUTH_REDIRECT_URI_COOKIE = "oauth_redirect_uri"
STATE_MAX_AGE = 600  # 10 minutes


def _cookie_secure(request: Request) -> bool:
    """
    True when we know the public request is HTTPS.
    Uses X-Forwarded-Proto when behind a proxy.
    """
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        return forwarded_proto.strip().lower() == "https"
    return (request.url.scheme or "").strip().lower() == "https"


def _normalize_state(val: str | None) -> str:
    # Cookies can be wrapped/serialized in unexpected ways; be defensive.
    return (val or "").strip().strip('"')


def _state_hash_short(val: str) -> str:
    # Avoid logging full secrets; hashes are enough to correlate mismatches.
    return hashlib.sha256(val.encode("utf-8")).hexdigest()[:12]


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return None


def _request_id(request: Request) -> str | None:
    rid = getattr(request.state, "request_id", None)
    return str(rid) if rid else None


def _redirect_with_tokens(access_token: str, refresh_token: str, next_url: str = "/dashboard") -> RedirectResponse:
    """Redirect to frontend with tokens in URL fragment so JS can store them and clear fragment."""
    fragment = f"access_token={access_token}&refresh_token={refresh_token}"
    url = f"{next_url}#{fragment}" if "#" not in next_url else f"{next_url}&{fragment}"
    return RedirectResponse(url=url, status_code=302)


# --- Google ---

def _google_redirect_uri(request: Request) -> str:
    """
    Build the Google redirect URI from the *public* origin so that the
    callback request lands on the same origin where we set cookies.
    """
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        forwarded_proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        base = f"{forwarded_proto.strip().lower()}://{forwarded_host.strip()}".rstrip("/")
        return f"{base}/auth/google/callback"

    # If APP_BASE_URL is explicitly set for production, prefer it (but don't
    # treat local dev defaults as production).
    base = (APP_BASE_URL or "").strip().rstrip("/")
    if base and not base.startswith("http://localhost") and not base.startswith("http://127.0.0.1"):
        return f"{base}/auth/google/callback"

    # Fallback: internal request base_url.
    fallback = str(request.base_url).rstrip("/")
    return f"{fallback}/auth/google/callback"


@router.get("/auth/google", include_in_schema=False)
async def auth_google(request: Request):
    """Redirect to Google OAuth consent. State and redirect_uri stored in cookies for CSRF and host consistency."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return RedirectResponse(url="/login?error=google_not_configured", status_code=302)
    state = secrets.token_urlsafe(32)
    redirect_uri = _google_redirect_uri(request)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    response = RedirectResponse(url=url, status_code=302)
    secure = _cookie_secure(request)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )
    response.set_cookie(
        key=OAUTH_REDIRECT_URI_COOKIE,
        value=redirect_uri,
        max_age=STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )
    return response


@router.get("/auth/google/callback", include_in_schema=False)
async def auth_google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        return RedirectResponse(url="/login?error=access_denied", status_code=302)
    if not code or not state:
        return RedirectResponse(url="/login?error=missing_params", status_code=302)

    secure = _cookie_secure(request)
    cookie_state = _normalize_state(request.cookies.get(OAUTH_STATE_COOKIE))
    state = _normalize_state(state)
    redirect_uri_cookie = _normalize_state(request.cookies.get(OAUTH_REDIRECT_URI_COOKIE))
    redirect_uri = redirect_uri_cookie or _google_redirect_uri(request)

    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        response = RedirectResponse(url="/login?error=invalid_state", status_code=302)
        logger.warning(
            "google_oauth_invalid_state request_id=%s cookie_state_len=%s state_len=%s cookie_state_hash=%s state_hash=%s",
            _request_id(request),
            len(cookie_state),
            len(state),
            _state_hash_short(cookie_state) if cookie_state else "none",
            _state_hash_short(state) if state else "none",
        )
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/", secure=secure, samesite="lax")
        response.delete_cookie(OAUTH_REDIRECT_URI_COOKIE, path="/", secure=secure, samesite="lax")
        return response

    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if token_resp.status_code != 200:
            resp = RedirectResponse(url="/login?error=token_exchange_failed", status_code=302)
            resp.delete_cookie(OAUTH_STATE_COOKIE, path="/", secure=secure, samesite="lax")
            resp.delete_cookie(OAUTH_REDIRECT_URI_COOKIE, path="/", secure=secure, samesite="lax")
            return resp

        token_data = token_resp.json()
        access_token_google = token_data.get("access_token")
        if not access_token_google:
            resp = RedirectResponse(url="/login?error=no_access_token", status_code=302)
            resp.delete_cookie(OAUTH_STATE_COOKIE, path="/", secure=secure, samesite="lax")
            resp.delete_cookie(OAUTH_REDIRECT_URI_COOKIE, path="/", secure=secure, samesite="lax")
            return resp

        async with httpx.AsyncClient() as client:
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token_google}"},
            )
        if userinfo_resp.status_code != 200:
            resp = RedirectResponse(url="/login?error=userinfo_failed", status_code=302)
            resp.delete_cookie(OAUTH_STATE_COOKIE, path="/", secure=secure, samesite="lax")
            resp.delete_cookie(OAUTH_REDIRECT_URI_COOKIE, path="/", secure=secure, samesite="lax")
            return resp

        userinfo = userinfo_resp.json()
        email = (userinfo.get("email") or "").strip()
        if not email:
            resp = RedirectResponse(url="/login?error=no_email", status_code=302)
            resp.delete_cookie(OAUTH_STATE_COOKIE, path="/", secure=secure, samesite="lax")
            resp.delete_cookie(OAUTH_REDIRECT_URI_COOKIE, path="/", secure=secure, samesite="lax")
            return resp

        sub = userinfo.get("sub") or ""
        first_name = (userinfo.get("given_name") or "").strip() or None
        last_name = (userinfo.get("family_name") or "").strip() or None

        res = ServiceFactory.get_service("UserResource")
        if not res:
            resp = RedirectResponse(url="/login?error=server", status_code=302)
            resp.delete_cookie(OAUTH_STATE_COOKIE, path="/", secure=secure, samesite="lax")
            resp.delete_cookie(OAUTH_REDIRECT_URI_COOKIE, path="/", secure=secure, samesite="lax")
            return resp
        row = res.find_or_create_oauth_user("google", sub, email, first_name, last_name)

        our_access = create_access_token(sub=str(row["id"]), email=row["email"])
        _session_id = create_session(row["id"], device_meta="oauth-google")
        our_refresh = create_refresh_token(row["id"], session_id=_session_id)
        write_audit_log(
            action="login",
            user_id=row["id"],
            ip_address=_client_ip(request),
            request_id=_request_id(request),
            details={"auth_provider": "google"},
        )

        response = _redirect_with_tokens(our_access, our_refresh)
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/", secure=secure, samesite="lax")
        response.delete_cookie(OAUTH_REDIRECT_URI_COOKIE, path="/", secure=secure, samesite="lax")
        return response
    except Exception as e:
        logger.exception("Google OAuth callback failed: %s", e)
        resp = RedirectResponse(url="/login?error=server", status_code=302)
        resp.delete_cookie(OAUTH_STATE_COOKIE, path="/", secure=secure, samesite="lax")
        resp.delete_cookie(OAUTH_REDIRECT_URI_COOKIE, path="/", secure=secure, samesite="lax")
        return resp


# --- Apple ---

def _apple_redirect_uri(request: Request) -> str:
    if APPLE_REDIRECT_URI:
        return APPLE_REDIRECT_URI.rstrip("/")

    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        forwarded_proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        base = f"{forwarded_proto.strip().lower()}://{forwarded_host.strip()}".rstrip("/")
        return f"{base}/auth/apple/callback"

    base = (APP_BASE_URL or "").strip().rstrip("/")
    if base:
        return f"{base}/auth/apple/callback"

    fallback = str(request.base_url).rstrip("/")
    return f"{fallback}/auth/apple/callback"


@router.get("/auth/apple", include_in_schema=False)
async def auth_apple(request: Request):
    """Redirect to Apple Sign In. State stored in cookie for CSRF check."""
    if not APPLE_CLIENT_ID:
        return RedirectResponse(url="/login?error=apple_not_configured", status_code=302)
    state = secrets.token_urlsafe(32)
    redirect_uri = _apple_redirect_uri(request)
    params = {
        "client_id": APPLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code id_token",
        "response_mode": "form_post",
        "scope": "email name",
        "state": state,
    }
    url = "https://appleid.apple.com/auth/authorize?" + urlencode(params)
    response = RedirectResponse(url=url, status_code=302)
    secure = _cookie_secure(request)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )
    return response


@router.post("/auth/apple/callback", include_in_schema=False)
async def auth_apple_callback_post(request: Request):
    """Apple POSTs to this endpoint with code, id_token, state, and optionally user (name, first time)."""
    form = await request.form()
    code = form.get("code")
    id_token = form.get("id_token")
    state = form.get("state")
    user_json = form.get("user")  # JSON string with name only on first auth

    if not state:
        return RedirectResponse(url="/login?error=missing_params", status_code=302)
    secure = _cookie_secure(request)
    cookie_state = _normalize_state(request.cookies.get(OAUTH_STATE_COOKIE))
    state = _normalize_state(state)
    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        response = RedirectResponse(url="/login?error=invalid_state", status_code=302)
        response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
        logger.warning(
            "apple_oauth_invalid_state request_id=%s cookie_state_len=%s state_len=%s cookie_state_hash=%s state_hash=%s",
            _request_id(request),
            len(cookie_state),
            len(state),
            _state_hash_short(cookie_state) if cookie_state else "none",
            _state_hash_short(state) if state else "none",
        )
        return response

    if not id_token:
        response = RedirectResponse(url="/login?error=no_id_token", status_code=302)
        response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
        return response

    # Decode and verify Apple id_token (JWT) with Apple's JWKS.
    import json
    from jose import jwt, jwk

    try:
        unverified = jwt.get_unverified_claims(id_token)
        kid = unverified.get("kid")
        if not kid:
            response = RedirectResponse(url="/login?error=invalid_id_token", status_code=302)
            response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
            return response

        async with httpx.AsyncClient() as client:
            jwks_resp = await client.get("https://appleid.apple.com/auth/keys")
        if jwks_resp.status_code != 200:
            response = RedirectResponse(url="/login?error=apple_keys_failed", status_code=302)
            response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
            return response

        jwks = jwks_resp.json()
        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = k
                break
        if not key:
            response = RedirectResponse(url="/login?error=invalid_id_token", status_code=302)
            response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
            return response

        public_key = jwk.construct(key)
        payload = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=APPLE_CLIENT_ID,
            issuer="https://appleid.apple.com",
        )
    except Exception:
        response = RedirectResponse(url="/login?error=invalid_id_token", status_code=302)
        response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
        return response

    sub = payload.get("sub") or ""
    email = (payload.get("email") or "").strip()
    if not sub:
        response = RedirectResponse(url="/login?error=no_apple_sub", status_code=302)
        response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
        return response

    first_name = None
    last_name = None
    if user_json:
        try:
            user_obj = json.loads(user_json)
            name = user_obj.get("name") or {}
            first_name = (name.get("firstName") or "").strip() or None
            last_name = (name.get("lastName") or "").strip() or None
        except Exception:
            pass

    if not email:
        # Apple may not send email after first time; we must look up by provider+sub
        res = ServiceFactory.get_service("UserResource")
        if res:
            row = res.get_raw_by_provider("apple", sub)
            if row:
                email = row.get("email") or ""
        if not email:
            response = RedirectResponse(url="/login?error=no_apple_email", status_code=302)
            response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
            return response

    res = ServiceFactory.get_service("UserResource")
    if not res:
        response = RedirectResponse(url="/login?error=server", status_code=302)
        response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
        return response
    row = res.find_or_create_oauth_user("apple", sub, email, first_name, last_name)

    our_access = create_access_token(sub=str(row["id"]), email=row["email"])
    _session_id = create_session(row["id"], device_meta="oauth-apple")
    our_refresh = create_refresh_token(row["id"], session_id=_session_id)
    write_audit_log(
        action="login",
        user_id=row["id"],
        ip_address=_client_ip(request),
        request_id=_request_id(request),
        details={"auth_provider": "apple"},
    )

    response = _redirect_with_tokens(our_access, our_refresh)
    response.delete_cookie(OAUTH_STATE_COOKIE, secure=secure, samesite="lax", path="/")
    return response
