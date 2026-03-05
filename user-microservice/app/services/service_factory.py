from framework.services.service_factory import BaseServiceFactory
from framework.services.data_access.PostgresRDBDataService import PostgresRDBDataService

from app.core.config import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME


class ServiceFactory(BaseServiceFactory):

    def __init__(self):
        super().__init__()

    @classmethod
    def get_service(cls, service_name):
        if service_name == "UserResource":
            import app.resources.user_resource as user_resource
            result = user_resource.UserResource(config=None)
        elif service_name == "UserResourceDataService":
            context = dict(
                user=DB_USER or "postgres",
                password=DB_PASSWORD or "postgres",
                host=DB_HOST or "localhost",
                port=int(DB_PORT) if DB_PORT else 5432,
                dbname=DB_NAME or "users_db",
            )
            data_service = PostgresRDBDataService(context=context)
            result = data_service
        else:
            result = None
        return result