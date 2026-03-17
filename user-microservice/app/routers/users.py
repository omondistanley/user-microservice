from typing import Any, List
import io
import json
import zipfile
from datetime import datetime
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm

from app.models.users import (
    NewUser,
    UserInfo,
    TokenResponse,
    RefreshRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserMeResponse,
    UserMeUpdate,
    ChangePasswordRequest,
    EmailValidateRequest,
)
from app.services.service_factory import ServiceFactory
from app.services.refresh_token_service import (
    create_refresh_token,
    get_refresh_token_info,
    revoke_all_refresh_tokens,
    validate_refresh_token,
)
from app.services.session_service import (
    create_session,
    list_sessions,
    revoke_all_sessions_except,
    revoke_session,
)
from app.services.password_reset_service import (
    create_reset_token,
    validate_and_consume_reset_token,
    set_password,
)
from app.services.email_verification_service import create_verification_token
from app.services.audit_log_service import write_audit_log
from app.services.account_service import delete_user_account
from app.core.security import verify_password, create_access_token
from app.core.dependencies import get_current_user
from app.core.rate_limit import rate_limit_dep
from app.core.config import (
    RATE_LIMIT_LOGIN_PER_MINUTE,
    RATE_LIMIT_REGISTER_PER_MINUTE,
    REQUIRE_EMAIL_VERIFICATION,
    EXPENSE_SERVICE_URL,
    BUDGET_SERVICE_URL,
    INVESTMENT_SERVICE_URL,
    INTERNAL_API_KEY,
)

router = APIRouter()


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


def _internal_headers(request_id: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if request_id:
        headers["x-request-id"] = request_id
    if INTERNAL_API_KEY:
        headers["x-internal-api-key"] = INTERNAL_API_KEY
    return headers


async def _purge_business_data(
    user_id: int,
    request_id: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    services = [
        ("expense", EXPENSE_SERVICE_URL, f"/internal/v1/users/{user_id}/expenses"),
        ("budget", BUDGET_SERVICE_URL, f"/internal/v1/users/{user_id}/budgets"),
        ("investment", INVESTMENT_SERVICE_URL, f"/internal/v1/users/{user_id}/holdings"),
    ]
    headers = _internal_headers(request_id)
    results: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for service_name, base_url, path in services:
            if not base_url:
                failure = {
                    "service": service_name,
                    "reason": "not_configured",
                    "status_code": None,
                }
                failures.append(failure)
                results[service_name] = {"status": "failed", **failure}
                continue

            try:
                response = await client.delete(f"{base_url}{path}", headers=headers)
            except Exception:
                failure = {
                    "service": service_name,
                    "reason": "network_error",
                    "status_code": None,
                }
                failures.append(failure)
                results[service_name] = {"status": "failed", **failure}
                continue

            if response.status_code not in (200, 204):
                details: Any = None
                try:
                    details = response.json()
                except Exception:
                    details = response.text[:300]
                failure = {
                    "service": service_name,
                    "reason": "http_error",
                    "status_code": response.status_code,
                    "details": details,
                }
                failures.append(failure)
                results[service_name] = {"status": "failed", **failure}
                continue

            payload: Any = None
            if response.status_code != 204 and (response.content or b""):
                try:
                    payload = response.json()
                except Exception:
                    payload = None
            results[service_name] = {
                "status": "ok",
                "status_code": response.status_code,
                "payload": payload,
            }

    return results, failures


@router.post("/token/refresh", tags=["auth"], response_model=TokenResponse)
async def token_refresh(body: RefreshRequest, request: Request):
    """Exchange a valid refresh token for a new access token and new refresh token (rotation)."""
    result = validate_refresh_token(body.refresh_token)
    ip_address = _client_ip(request)
    request_id = _request_id(request)

    if result.status == "reused":
        if result.session_id and result.user_id:
            revoke_session(result.session_id, result.user_id)
        write_audit_log(
            action="token_refresh_reuse_detected",
            user_id=result.user_id,
            ip_address=ip_address,
            request_id=request_id,
            details={"family_id": result.family_id, "session_id": result.session_id},
        )
        raise HTTPException(status_code=401, detail="Refresh token reuse detected. Please sign in again.")

    if result.status != "ok" or result.user_id is None or not result.email:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    access_token = create_access_token(sub=str(result.user_id), email=result.email)
    refresh_token = create_refresh_token(
        result.user_id,
        family_id=result.family_id,
        session_id=result.session_id,
    )
    write_audit_log(
        action="token_refresh",
        user_id=result.user_id,
        ip_address=ip_address,
        request_id=request_id,
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
    )


@router.post("/login", tags=["auth"], response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    _: None = Depends(rate_limit_dep(RATE_LIMIT_LOGIN_PER_MINUTE)),
):
    """Username = email. Returns JWT access token."""
    res = ServiceFactory.get_service("UserResource")
    if res is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    row = res.get_raw_by_email(form_data.username)
    if row is None:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not row.get("password_hash"):
        raise HTTPException(status_code=401, detail="Account has no password set")
    if not verify_password(form_data.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if REQUIRE_EMAIL_VERIFICATION and not row.get("email_verified_at"):
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before signing in. Check your inbox for the verification link.",
        )
    token = create_access_token(sub=str(row["id"]), email=row["email"])
    device_meta = (request.headers.get("user-agent") or "")[:512]
    session_id = create_session(row["id"], device_meta=device_meta)
    refresh = create_refresh_token(row["id"], session_id=session_id)
    write_audit_log(
        action="login",
        user_id=row["id"],
        ip_address=_client_ip(request),
        request_id=_request_id(request),
        details={"auth_provider": row.get("auth_provider") or "password"},
    )
    return TokenResponse(access_token=token, token_type="bearer", refresh_token=refresh)


@router.get("/user/{email}", tags=["users"])
async def get_user(email: str, current_user: dict = Depends(get_current_user)) -> UserInfo:
    res = ServiceFactory.get_service("UserResource")
    if res is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    result = res.get_by_key(email)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    if current_user["email"] != email:
        raise HTTPException(status_code=403, detail="Not allowed to view this user")
    return result

@router.get("/users", tags=["users"], response_model=List[UserInfo])
async def get_users(page: int = 1, pagesize: int = 10, current_user: dict = Depends(get_current_user)) -> List[UserInfo]:
    res = ServiceFactory.get_service("UserResource")
    if res is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    users = res.get_all(page = page, pagesize = pagesize)
    if not users:
        raise HTTPException(status_code=404, detail="No users found")
    return users

@router.post("/forgot-password", tags=["auth"])
async def forgot_password(body: ForgotPasswordRequest):
    """Send reset link to email if user exists. Always returns same message (no enumeration)."""
    create_reset_token(body.email)
    return {"message": "If an account exists with this email, you will receive a password reset link."}


@router.post("/reset-password", tags=["auth"])
async def reset_password(body: ResetPasswordRequest, request: Request):
    """Reset password using token from email link."""
    user_id = validate_and_consume_reset_token(body.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    set_password(user_id, body.new_password)
    revoke_all_refresh_tokens(user_id)
    write_audit_log(
        action="password_change",
        user_id=user_id,
        ip_address=_client_ip(request),
        request_id=_request_id(request),
    )
    return {"message": "Password has been reset. You can log in now."}


@router.post("/user", tags=["users"], response_model=UserInfo)
async def newuser(
    newUser: NewUser,
    _: None = Depends(rate_limit_dep(RATE_LIMIT_REGISTER_PER_MINUTE)),
):  # public: no auth required for registration
    res = ServiceFactory.get_service("UserResource")
    if res is None:
        raise HTTPException(status_code=500, detail="Internal server error")

    try:
        new_user = res.new_user(newUser)
        if not new_user:
            raise HTTPException(status_code=400, detail="Registration failed")
        try:
            create_verification_token(new_user.id, new_user.email)
        except Exception:
            pass
        return new_user
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@router.get("/user/me", tags=["users"], response_model=UserMeResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return full profile of the currently authenticated user."""
    user_id = int(current_user["id"])
    data_svc = ServiceFactory.get_service("UserResourceDataService")
    if not data_svc:
        raise HTTPException(status_code=500, detail="Internal server error")
    row = data_svc.get_data_object("users_db", "user", key_field="id", key_value=user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserMeResponse(
        id=int(row["id"]),
        email=row["email"],
        first_name=row.get("first_name"),
        last_name=row.get("last_name"),
        created_at=row.get("created_at"),
        auth_provider=row.get("auth_provider"),
    )


@router.patch("/user/me", tags=["users"], response_model=UserMeResponse)
async def patch_me(
    body: UserMeUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Update name and/or email of the current user."""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from app.core.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

    user_id = int(current_user["id"])
    updates: dict = {}
    if body.first_name is not None:
        updates["first_name"] = body.first_name.strip()
    if body.last_name is not None:
        updates["last_name"] = body.last_name.strip()
    if body.email is not None:
        updates["email"] = str(body.email).strip().lower()
    if not updates:
        # Nothing to update — return current profile
        return await get_me(current_user)
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id]
    conn = psycopg2.connect(
        host=DB_HOST or "localhost",
        port=int(DB_PORT) if DB_PORT else 5432,
        user=DB_USER or "postgres",
        password=DB_PASSWORD or "postgres",
        dbname=DB_NAME or "users_db",
        cursor_factory=RealDictCursor,
    )
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            f'UPDATE users_db."user" SET {set_clause} WHERE id = %s RETURNING id, email, first_name, last_name, created_at, auth_provider',
            values,
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        write_audit_log(
            action="profile_update",
            user_id=user_id,
            ip_address=_client_ip(request),
            request_id=_request_id(request),
            details={"fields": list(updates.keys())},
        )
        return UserMeResponse(
            id=int(row["id"]),
            email=row["email"],
            first_name=row.get("first_name"),
            last_name=row.get("last_name"),
            created_at=row.get("created_at"),
            auth_provider=row.get("auth_provider"),
        )
    finally:
        conn.close()


@router.post("/user/me/password", tags=["users"])
async def change_my_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Change password: verify current password then hash and store new one."""
    res = ServiceFactory.get_service("UserResource")
    if not res:
        raise HTTPException(status_code=500, detail="Internal server error")
    row = res.get_raw_by_email(current_user["email"])
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    if not row.get("password_hash"):
        raise HTTPException(status_code=400, detail="Account uses social login; password cannot be changed here.")
    if not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    user_id = int(current_user["id"])
    set_password(user_id, body.new_password)
    revoke_all_refresh_tokens(user_id)
    write_audit_log(
        action="password_change",
        user_id=user_id,
        ip_address=_client_ip(request),
        request_id=_request_id(request),
    )
    return {"message": "Password updated. Please sign in again on all devices."}


@router.delete("/user/me", tags=["users"], status_code=204)
async def delete_me(request: Request, current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    ip_address = _client_ip(request)
    request_id = _request_id(request)

    write_audit_log(
        action="delete_account_requested",
        user_id=user_id,
        ip_address=ip_address,
        request_id=request_id,
    )

    purge_results, purge_failures = await _purge_business_data(user_id, request_id)
    if purge_failures:
        write_audit_log(
            action="delete_account_purge_failed",
            user_id=user_id,
            ip_address=ip_address,
            request_id=request_id,
            details={
                "rollback": "not_performed",
                "failures": purge_failures,
                "results": purge_results,
            },
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Failed to purge account data in dependent services",
                "rollback": "not_performed",
                "failures": purge_failures,
            },
        )

    revoke_all_refresh_tokens(user_id)
    if not delete_user_account(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    write_audit_log(
        action="delete_account",
        user_id=user_id,
        ip_address=ip_address,
        request_id=request_id,
        details={"purge_results": purge_results},
    )
    return None


@router.get("/user/me/export", tags=["users"])
async def export_me(
    request: Request,
    current_user: dict = Depends(get_current_user),
    convert_to: str | None = Query(None, min_length=3, max_length=3),
):
    user_id = int(current_user["id"])
    request_id = _request_id(request)
    ip_address = _client_ip(request)
    auth_header = request.headers.get("authorization")
    headers = {"authorization": auth_header} if auth_header else {}

    # Fetch current user row for richer export.
    data_service = ServiceFactory.get_service("UserResourceDataService")
    user_row = None
    if data_service is not None:
        user_row = data_service.get_data_object(
            "users_db", "user", key_field="id", key_value=user_id
        )

    expenses_payload = {"items": [], "total": 0}
    budgets_payload = {"items": [], "total": 0}
    warnings: list[str] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        if EXPENSE_SERVICE_URL:
            try:
                query_items = {"format": "json"}
                if convert_to and len(convert_to.strip()) == 3:
                    query_items["convert_to"] = convert_to.strip().upper()
                qs = urlencode(query_items)
                resp = await client.get(
                    f"{EXPENSE_SERVICE_URL}/api/v1/expenses/export?{qs}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, dict):
                        expenses_payload = payload
                else:
                    warnings.append(f"expense_export_failed:{resp.status_code}")
            except Exception:
                warnings.append("expense_export_failed:network_error")
        else:
            warnings.append("expense_export_failed:not_configured")

        if BUDGET_SERVICE_URL:
            try:
                resp = await client.get(
                    f"{BUDGET_SERVICE_URL}/api/v1/budgets?page=1&page_size=1000&include_inactive=true",
                    headers=headers,
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, dict):
                        budgets_payload = payload
                else:
                    warnings.append(f"budget_export_failed:{resp.status_code}")
            except Exception:
                warnings.append("budget_export_failed:network_error")
        else:
            warnings.append("budget_export_failed:not_configured")

    export_payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user": user_row or {"id": user_id, "email": current_user.get("email")},
        "expenses": expenses_payload,
        "budgets": budgets_payload,
        "convert_to": convert_to.strip().upper() if convert_to and len(convert_to.strip()) == 3 else None,
        "warnings": warnings,
    }

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("export.json", json.dumps(export_payload, default=str, indent=2))
    zip_buffer.seek(0)

    write_audit_log(
        action="export",
        user_id=user_id,
        ip_address=ip_address,
        request_id=request_id,
        details={
            "expense_items": len(expenses_payload.get("items", [])) if isinstance(expenses_payload, dict) else 0,
            "budget_items": len(budgets_payload.get("items", [])) if isinstance(budgets_payload, dict) else 0,
        },
    )
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="my_data_export.zip"'},
    )


@router.post("/api/v1/validate-email", tags=["auth"])
async def validate_email_address(body: EmailValidateRequest):
    """
    Proxy to Rapid Email Validator API. Validates email syntax, MX records,
    disposable domain detection, and role-based address checks.
    Configure via RAPID_EMAIL_VALIDATOR_KEY env var (RapidAPI key).
    Returns { valid: bool, disposable: bool, role_based: bool, reason: str }.
    """
    import os
    api_key = os.environ.get("RAPID_EMAIL_VALIDATOR_KEY", "")
    email = str(body.email).strip().lower()

    if not api_key:
        # No API key configured — do basic syntax + domain validation only
        import re
        valid_syntax = bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))
        return {
            "valid": valid_syntax,
            "disposable": False,
            "role_based": False,
            "reason": "basic_check" if valid_syntax else "invalid_syntax",
            "configured": False,
        }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://emailvalidation.abstractapi.com/v1/",
                params={"api_key": api_key, "email": email},
            )
        if resp.status_code != 200:
            return {"valid": True, "disposable": False, "role_based": False, "reason": "api_error", "configured": True}
        data = resp.json()
        is_valid_format = data.get("is_valid_format", {})
        is_disposable = data.get("is_disposable_email", {})
        is_role = data.get("is_role_email", {})
        deliverability = (data.get("deliverability") or "").upper()
        valid = (
            (isinstance(is_valid_format, dict) and is_valid_format.get("value", True))
            and deliverability in ("DELIVERABLE", "UNKNOWN", "")
        )
        disposable = isinstance(is_disposable, dict) and bool(is_disposable.get("value", False))
        role_based = isinstance(is_role, dict) and bool(is_role.get("value", False))
        reason = "ok"
        if not valid:
            reason = "undeliverable"
        elif disposable:
            reason = "disposable"
        elif role_based:
            reason = "role_based"
        return {
            "valid": valid,
            "disposable": disposable,
            "role_based": role_based,
            "reason": reason,
            "configured": True,
        }
    except Exception:
        return {"valid": True, "disposable": False, "role_based": False, "reason": "api_timeout", "configured": True}
