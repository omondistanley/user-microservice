from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.config import INTERNAL_API_KEY
from app.core.dependencies import get_current_user
from app.models.users import (
    NotificationInternalCreate,
    NotificationListResponse,
    NotificationResponse,
)
from app.services.notification_service import (
    create_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)

router = APIRouter()


def _validate_internal_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    if INTERNAL_API_KEY and x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


@router.get("/api/v1/notifications", tags=["notifications"], response_model=NotificationListResponse)
async def get_notifications(
    current_user: dict = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    user_id = int(current_user["id"])
    offset = (page - 1) * page_size
    items, total, unread = list_notifications(user_id=user_id, limit=page_size, offset=offset)
    return NotificationListResponse(items=items, total=total, unread=unread)


@router.patch(
    "/api/v1/notifications/{notification_id}/read",
    tags=["notifications"],
    response_model=NotificationResponse,
)
async def mark_notification_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        nid = UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification id")
    user_id = int(current_user["id"])
    row = mark_notification_read(user_id=user_id, notification_id=str(nid))
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationResponse(**row)


@router.patch("/api/v1/notifications/read-all", tags=["notifications"], response_model=dict)
async def mark_all_as_read(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    updated_count = mark_all_notifications_read(user_id=user_id)
    return {"updated": updated_count}


@router.post(
    "/internal/v1/notifications/budget-alert",
    tags=["notifications"],
    response_model=NotificationResponse,
)
async def create_budget_alert_notification(
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
    return NotificationResponse(**row)
