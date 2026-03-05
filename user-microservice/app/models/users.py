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

class UserInfo(Hatoas): # return the user information with id, email, and last_name
    id: int
    email: EmailStr
    last_name: str

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


class UserSettingsUpdate(BaseModel):
    default_currency: str = Field(..., min_length=3, max_length=3)
