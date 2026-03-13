"""Phase 5: Session list and revoke-all-except-current (no 2FA)."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.services.refresh_token_service import get_refresh_token_info
from app.services.session_service import list_sessions, revoke_all_sessions_except

router = APIRouter()


class RevokeAllExceptRequest(BaseModel):
    """Body for POST /api/v1/sessions/revoke-all-except-current. Current session is identified by this refresh token."""
    refresh_token: str


@router.get("/api/v1/sessions")
async def get_sessions(current_user: dict = Depends(get_current_user)):
    """List active sessions for the current user."""
    user_id = int(current_user["id"])
    rows = list_sessions(user_id, include_revoked=False)
    return {
        "items": [
            {
                "session_id": str(r["session_id"]),
                "device_meta": r.get("device_meta"),
                "issued_at": r["issued_at"],
                "last_seen_at": r["last_seen_at"],
            }
            for r in rows
        ],
    }


@router.post("/api/v1/sessions/revoke-all-except-current")
async def revoke_all_except_current(
    body: RevokeAllExceptRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Revoke all other sessions (and their refresh tokens) for the current user.
    The session that holds the given refresh_token is kept. Requires valid JWT and matching user.
    """
    if not body.refresh_token or not body.refresh_token.strip():
        raise HTTPException(status_code=400, detail="refresh_token is required")
    user_id, session_id = get_refresh_token_info(body.refresh_token.strip())
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired refresh token")
    current_id = int(current_user["id"])
    if user_id != current_id:
        raise HTTPException(status_code=403, detail="Refresh token does not belong to current user")
    count = revoke_all_sessions_except(current_id, except_session_id=session_id)
    return {"revoked_sessions": count, "message": "All other sessions have been revoked."}
