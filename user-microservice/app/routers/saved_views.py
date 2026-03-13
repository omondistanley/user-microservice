"""Phase 4: Saved report views API."""
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user
from app.services.saved_views_service import (
    create_saved_view,
    list_saved_views,
    get_saved_view,
    delete_saved_view,
)

router = APIRouter()


@router.post("/api/v1/reports/saved-views")
async def post_saved_view(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """Create a saved view. Body: { \"name\": \"...\", \"payload\": { ... } }."""
    user_id = int(current_user["id"])
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    view_payload = payload.get("payload")
    if view_payload is not None and not isinstance(view_payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")
    row = create_saved_view(user_id, name, view_payload or {})
    return {
        "view_id": str(row["view_id"]),
        "user_id": row["user_id"],
        "name": row["name"],
        "payload": row.get("payload_json") or {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("/api/v1/reports/saved-views")
async def get_saved_views_list(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    rows = list_saved_views(user_id)
    return {
        "items": [
            {
                "view_id": str(r["view_id"]),
                "user_id": r["user_id"],
                "name": r["name"],
                "payload": r.get("payload_json") or {},
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ],
    }


@router.delete("/api/v1/reports/saved-views/{view_id}", status_code=204)
async def delete_saved_view_route(
    view_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        UUID(view_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid view_id")
    user_id = int(current_user["id"])
    if not delete_saved_view(view_id, user_id):
        raise HTTPException(status_code=404, detail="Saved view not found")
