from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class NewUser(BaseModel):
    email: EmailStr
    last_name: str
    first_name: str

class UserInfo(NewUser):
    id: int
    last_name: str
    first_name: str

class User(BaseModel):
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