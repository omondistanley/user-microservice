from __future__ import annotations
from typing import Dict, List, Any
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

class Hatoas(BaseModel): # return the links with self, budgets, and expenses
    links: Dict[str, Any]

class NewUser(BaseModel): # create a new user with password, email, last_name, and first_name
    email: EmailStr
    last_name: str
    first_name: str
    password: str = Field(..., min_length=8)

class TokenResponse(BaseModel):  # access token and optional refresh token
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None


class RefreshRequest(BaseModel):  # body for POST /token/refresh
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

class UserInfo(BaseModel): # return the user information with id, email, first_name, and last_name
    id: int
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserMeResponse(BaseModel):
    """Current user profile for GET /user/me."""
    id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email_verified_at: Optional[datetime] = None


class UserMeUpdate(BaseModel):
    """Body for PATCH /user/me."""
    first_name: Optional[str] = Field(None, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)


class ChangePasswordRequest(BaseModel):
    """Body for POST /user/me/change-password."""
    current_password: str
    new_password: str = Field(..., min_length=8)

class User(BaseModel): # return the user information with id, email, last_name, first_name, created_at, and modified_at
    id: Optional[int] = None
    email: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "email": "jamesdoe@gmail.com",
                "last_name": "Doe",
                "first_name": "Jam",
                "created_at": "2024-10-01 18:53:10",
                "modified_at": "2024-10-01 18:54:10",
            }
        }


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
    updated_at: datetime
    active_household_id: Optional[UUID] = None


class UserSettingsUpdate(BaseModel):
    default_currency: str = Field(..., min_length=3, max_length=3)


class ActiveHouseholdUpdate(BaseModel):
    """Body for PATCH /api/v1/settings/active-household. null = personal scope."""
    household_id: Optional[UUID] = None


# --- Households (Phase 3) ---

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


class UserMeResponse(BaseModel):
    id: int
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: Optional[datetime] = None
    auth_provider: Optional[str] = None


class UserMeUpdate(BaseModel):
    first_name: Optional[str] = Field(None, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class EmailValidateRequest(BaseModel):
    email: EmailStr
