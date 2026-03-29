from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user
from app.models.users import ActiveHouseholdUpdate, UserSettingsResponse, UserSettingsUpdate
from app.services.household_service import set_active_household
from app.services.user_settings_service import get_user_settings, update_user_settings

router = APIRouter()


@router.get("/api/v1/settings", tags=["settings"], response_model=UserSettingsResponse)
async def get_settings(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    row = get_user_settings(user_id)
    return UserSettingsResponse(**row)


@router.patch("/api/v1/settings", tags=["settings"], response_model=UserSettingsResponse)
async def patch_settings(payload: UserSettingsUpdate, current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    current = get_user_settings(user_id)
    try:
        row = update_user_settings(
            user_id,
            default_currency=payload.default_currency if payload.default_currency is not None else current.get("default_currency"),
            theme_preference=payload.theme_preference if payload.theme_preference is not None else current.get("theme_preference"),
            push_notifications_enabled=(
                payload.push_notifications_enabled
                if payload.push_notifications_enabled is not None
                else current.get("push_notifications_enabled")
            ),
            email_notifications_enabled=(
                payload.email_notifications_enabled
                if payload.email_notifications_enabled is not None
                else current.get("email_notifications_enabled")
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return UserSettingsResponse(**row)


@router.patch("/api/v1/settings/active-household", tags=["settings"], response_model=UserSettingsResponse)
async def patch_active_household(payload: ActiveHouseholdUpdate, current_user: dict = Depends(get_current_user)):
    """Set active household scope (null = personal). User must be active member of the household."""
    user_id = int(current_user["id"])
    try:
        set_active_household(user_id, str(payload.household_id) if payload.household_id is not None else None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    row = get_user_settings(user_id)
    return UserSettingsResponse(**row)
