from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user
from app.models.users import UserSettingsResponse, UserSettingsUpdate
from app.services.user_settings_service import get_user_settings, update_default_currency

router = APIRouter()


@router.get("/api/v1/settings", tags=["settings"], response_model=UserSettingsResponse)
async def get_settings(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    row = get_user_settings(user_id)
    return UserSettingsResponse(**row)


@router.patch("/api/v1/settings", tags=["settings"], response_model=UserSettingsResponse)
async def patch_settings(payload: UserSettingsUpdate, current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["id"])
    try:
        row = update_default_currency(user_id, payload.default_currency)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return UserSettingsResponse(**row)
