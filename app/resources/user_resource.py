from datetime import datetime
from typing import Any

from fastapi.openapi.utils import status_code_ranges
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import insert
from sqlalchemy.testing.suite.test_reflection import users

from framework.resources.base_resource import BaseResource
from app.models.users import User, NewUser, UserInfo
from app.services.service_factory import ServiceFactory


class UserResource(BaseResource):

    def __init__(self, config):
        super().__init__(config)

        # TODO -- Replace with dependency injection.
        #
        self.data_service = ServiceFactory.get_service("UserResourceDataService")
        self.database = "users_db"
        self.collection = "user"
        self.key_field="email"

    def get_by_key(self, key: str) -> User:

        d_service = self.data_service

        result = d_service.get_data_object(
            self.database, self.collection, key_field=self.key_field, key_value=key
        )
        if result is None:
            raise HTTPException(status_code=404, detail="User Not Found")
        result = User(**result)
        return result

    def get_all(self, page: int = 1, pagesize:int = 10) -> list[User]:
        usersservice = self.data_service
        offset = (page - 1) * pagesize
        result = usersservice.get_data_object(self.database, self.collection, limit=pagesize, offset=offset)
        users = [User(**result) for result in result]
        return users


    def new_user(self, user: NewUser) -> UserInfo:
        try:
            user_info = user.dict()
            user_info['created_at'] = datetime.now()
            user_info['modified_at'] = datetime.now()

            newuser = self.data_service.create_data_object(self.database, self.collection, user_info)
            if newuser is None:
                raise HTTPException(status_code=500, detail="Registration error")
            return UserInfo(**newuser)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")