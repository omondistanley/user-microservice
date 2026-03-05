from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from framework.resources.base_resource import BaseResource
from app.models.users import NewUser, UserInfo
from app.services.service_factory import ServiceFactory
from app.core.security import hash_password


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
        return UserInfo(id=result["id"], email=result["email"], last_name=result["last_name"], links=hatoaslinks)

    def get_all(self, page: int = 1, pagesize:int = 10) -> list[UserInfo]:
        usersservice = self.data_service
        offset = (page - 1) * pagesize
        result = usersservice.get_data_objects(self.database, self.collection, limit=pagesize, offset=offset)
        users = []
        for user in result:
            hatoaslinks = {
                "self": {"href": f"/user/{user['id']}"},
                "budgets": {"href": f"/user/{user['id']}/budgets"},
                "expenses": {"href": f"/user/{user['id']}/expenses"}
            }
            users.append(UserInfo(id=user["id"], email=user["email"], last_name=user["last_name"], links=hatoaslinks))
        return users


    def get_raw_by_email(self, email: str) -> dict | None:
        """Return raw user row (including password_hash) for auth only. Never expose in responses."""
        return self.data_service.get_data_object(
            self.database, self.collection, key_field=self.key_field, key_value=email
        )

    def get_raw_by_provider(self, auth_provider: str, auth_provider_sub: str) -> dict | None:
        """Return raw user row by OAuth provider and provider subject."""
        return self.data_service.get_data_object_where(
            self.database, self.collection,
            {"auth_provider": auth_provider, "auth_provider_sub": auth_provider_sub},
        )

    def find_or_create_oauth_user(
        self,
        auth_provider: str,
        auth_provider_sub: str,
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict:
        """
        Find user by provider+sub; if not found, by email (then link); else create.
        Returns raw user row. Provider users are treated as email-verified.
        """
        now = datetime.now(timezone.utc)
        # 1) By provider + sub
        row = self.get_raw_by_provider(auth_provider, auth_provider_sub)
        if row:
            if not row.get("email_verified_at"):
                self.data_service.update_data_object(
                    self.database, self.collection, row["id"],
                    {"email_verified_at": now, "modified_at": now},
                )
                row["email_verified_at"] = now
            return row
        # 2) By email (link existing account)
        row = self.get_raw_by_email(email)
        if row:
            self.data_service.update_data_object(
                self.database, self.collection, row["id"],
                {
                    "auth_provider": auth_provider,
                    "auth_provider_sub": auth_provider_sub,
                    "email_verified_at": now,
                    "modified_at": now,
                },
            )
            row["auth_provider"] = auth_provider
            row["auth_provider_sub"] = auth_provider_sub
            row["email_verified_at"] = now
            return row
        # 3) Create new user
        user_info: dict[str, Any] = {
            "email": email,
            "first_name": first_name or "",
            "last_name": last_name or "",
            "password_hash": None,
            "auth_provider": auth_provider,
            "auth_provider_sub": auth_provider_sub,
            "email_verified_at": now,
            "created_at": now,
            "modified_at": now,
        }
        newuser = self.data_service.create_data_object(self.database, self.collection, user_info)
        return newuser

    def new_user(self, user: NewUser) -> UserInfo:
        try:
            user_info = user.model_dump(exclude={"password"})
            user_info["password_hash"] = hash_password(user.password)
            user_info["created_at"] = datetime.now()
            user_info["modified_at"] = datetime.now()

            newuser = self.data_service.create_data_object(self.database, self.collection, user_info)
            if newuser is None:
                raise HTTPException(status_code=500, detail="Registration error")
            hatoaslinks = {
                "self": {"href": f"/user/{newuser['id']}"},
                "budgets": {"href": f"/user/{newuser['id']}/budgets"},
                "expenses": {"href": f"/user/{newuser['id']}/expenses"}
            }
            return UserInfo(id=newuser["id"], email=newuser["email"], last_name=newuser["last_name"], links=hatoaslinks)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")