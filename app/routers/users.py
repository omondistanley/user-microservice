from fastapi import APIRouter, Depends, HTTPException
from oauthlib.uri_validate import userinfo

from app.models.users import User,  NewUser
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
async def get_users() -> List[User]:
    res = ServiceFactory.get_service("UserResource")
    if res is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    users = res.get_all()
    if not users:
        raise HTTPException(status_code=404, detail="No users found")
    return users

'''@router.post("/user", tags=["users"], response_model=User)
async def newuser(user: User):
    res = ServiceFactory.get_service("UserResource")
    if res is None:
        raise HTTPException(status_code=500, detail="Internal server error")
    nuser = res.newuser(userinfo)
    if not nuser:
        raise HTTPException(status_code=500, detail="Internal server error")
    user = User(**nuser)
    return user'''

