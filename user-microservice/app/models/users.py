from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Hatoas(BaseModel):
    links: Dict[str, Any]


class NewUser(BaseModel):
    email: EmailStr
    last_name: str
    first_name: str
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class UserInfo(BaseModel):
    id: int
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    links: Optional[Dict[str, Any]] = None


class UserMeResponse(BaseModel):
    id: int
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    created_at: Optional[datetime] = None
    email_verified_at: Optional[datetime] = None
    auth_provider: Optional[str] = None


class UserMeUpdate(BaseModel):
    first_name: Optional[str] = Field(None, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None, max_length=1000)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class User(BaseModel):
    id: Optional[int] = None
    email: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    bio: Optional[str] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "email": "jamesdoe@gmail.com",
                "last_name": "Doe",
                "first_name": "Jam",
                "bio": "Budgeting for travel and long-term investing.",
                "created_at": "2024-10-01 18:53:10",
                "modified_at": "2024-10-01 18:54:10",
            }
        }
    )


class NotificationResponse(BaseModel):
    notification_id: UUID
    user_id: int
    type: str
    title: str
    body: str
    is_read: bool
    payload_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread: int


class NotificationInternalCreate(BaseModel):
    user_id: int
    type: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    payload: Optional[Dict[str, Any]] = None


class UserSettingsResponse(BaseModel):
    user_id: int
    default_currency: str
    theme_preference: str
    push_notifications_enabled: bool
    email_notifications_enabled: bool
    updated_at: datetime
    active_household_id: Optional[UUID] = None


class UserSettingsUpdate(BaseModel):
    default_currency: Optional[str] = Field(None, min_length=3, max_length=3)
    theme_preference: Optional[str] = Field(None, pattern="^(light|dark|system)$")
    push_notifications_enabled: Optional[bool] = None
    email_notifications_enabled: Optional[bool] = None


class ActiveHouseholdUpdate(BaseModel):
    """Body for PATCH /api/v1/settings/active-household. null = personal scope."""

    household_id: Optional[UUID] = None


class HouseholdCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class HouseholdResponse(BaseModel):
    household_id: UUID
    owner_user_id: int
    name: str
    created_at: datetime
    updated_at: datetime
    role: Optional[str] = None
    status: Optional[str] = None


class HouseholdMemberResponse(BaseModel):
    household_id: UUID
    user_id: int
    role: str
    status: str
    invited_by_user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HouseholdMemberInvite(BaseModel):
    """Invite by email (user must exist)."""

    email: EmailStr
    role: str = Field("member", min_length=1, max_length=32)


class HouseholdMemberUpdate(BaseModel):
    role: Optional[str] = Field(None, min_length=1, max_length=32)
    status: Optional[str] = Field(None, min_length=1, max_length=32)


class UserScopeResponse(BaseModel):
    """Response for GET /internal/v1/users/me/scope (for expense/budget to resolve scope)."""

    user_id: int
    active_household_id: Optional[UUID] = None


class EmailValidateRequest(BaseModel):
    email: EmailStr
