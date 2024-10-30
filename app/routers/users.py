from logging import lastResort

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from oauthlib.uri_validate import userinfo
from app.models.users import User,  NewUser, UserInfo
from app.resources.user_resource import UserResource
from app.services.service_factory import ServiceFactory
from typing import List

router = APIRouter()


@router.get("/user/{email}", tags=["users"])
async def get_user(email: str) -> User:

    # TODO Do lifecycle management for singleton resource
    res = ServiceFactory.get_service("UserResource")
    if res is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    result = res.get_by_key(email)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result

@router.get('/users', tags=["users"], response_model=List[User])
async def get_users(page: int = 1, pagesize: int = 10) -> List[User]:
    res = ServiceFactory.get_service("UserResource")
    if res is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    users = res.get_all(page = page, pagesize = pagesize)
    if not users:
        raise HTTPException(status_code=404, detail="No users found")
    return users

@router.post("/user", tags=["users"], response_model=UserInfo)
async def newuser(newUser: NewUser):
    res = ServiceFactory.get_service("UserResource")
    if res is None:
        raise HTTPException(status_code=500, detail="Internal server error")

    try:
        new_user = res.new_user(newUser)
        if not new_user:
            raise HTTPException(status_code=400, detail="Registration failed")
        return new_user
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

