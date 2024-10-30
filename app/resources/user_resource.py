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

    def get_by_key(self, key: str) -> UserInfo:

        d_service = self.data_service

        result = d_service.get_data_object(
            self.database, self.collection, key_field=self.key_field, key_value=key
        )
        if result is None:
            raise HTTPException(status_code=404, detail="User Not Found")
        hatoaslinks = {
            "self": {"href": f"/user/{result['id']}"},
            "budgets": {"href": f"/user/{result['id']}/budgets"},
            "expenses": {"href": f"/user/{result['id']}/expenses"}
        }
        return UserInfo(**result, links=hatoaslinks)

    def get_all(self, page: int = 1, pagesize:int = 10) -> list[UserInfo]:
        usersservice = self.data_service
        offset = (page - 1) * pagesize
        result = usersservice.get_data_object(self.database, self.collection, limit=pagesize, offset=offset)
        users = []
        for user in result:
            hatoaslinks = {
                "self": {"href": f"/user/{user['id']}"},
                "budgets": {"href": f"/user/{user['id']}/budgets"},
                "expenses": {"href": f"/user/{user['id']}/expenses"}
            }
            users.append(UserInfo(**user, link=hatoaslinks))
        return users


    def new_user(self, user: NewUser) -> UserInfo:
        try:
            user_info = user.dict()
            user_info['created_at'] = datetime.now()
            user_info['modified_at'] = datetime.now()

            newuser = self.data_service.create_data_object(self.database, self.collection, user_info)
            if newuser is None:
                raise HTTPException(status_code=500, detail="Registration error")
            hatoaslinks = {
                "self": {"href": f"/user/{newuser['id']}"},
                "budgets":{"href": f"/user/{newuser['id']}/budgets"},
                "expenses": {"href": f"/user/{newuser['id']}/expenses"}
            }
            return UserInfo(**newuser, links =hatoaslinks)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")