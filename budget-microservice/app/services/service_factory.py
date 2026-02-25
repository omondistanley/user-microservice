from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
)
from app.resources.budget_resource import BudgetResource
from app.services.budget_data_service import BudgetDataService
from framework.services.service_factory import BaseServiceFactory


class ServiceFactory(BaseServiceFactory):
    @classmethod
    def get_service(cls, service_name: str):
        if service_name == "BudgetResource":
            res = BudgetResource(config=None)
            res.data_service = cls.get_service("BudgetDataService")  # type: ignore
            return res
        if service_name == "BudgetDataService":
            context = {
                "user": DB_USER or "postgres",
                "password": DB_PASSWORD or "postgres",
                "host": DB_HOST or "localhost",
                "port": int(DB_PORT) if DB_PORT else 5432,
                "dbname": DB_NAME or "budgets_db",
            }
            return BudgetDataService(context=context)
        return None
