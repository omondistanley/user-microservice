from pathlib import Path

from app.core.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    RECEIPT_STORAGE_BACKEND,
    RECEIPT_STORAGE_PATH,
)
from app.resources.expense_resource import ExpenseResource
from app.services.expense_data_service import ExpenseDataService
from app.services.plaid_data_service import PlaidDataService
from app.services.receipt_service import ReceiptService
from app.services.receipt_storage import LocalReceiptStorage
from framework.services.service_factory import BaseServiceFactory


def _db_context():
    return {
        "user": DB_USER or "postgres",
        "password": DB_PASSWORD or "postgres",
        "host": DB_HOST or "localhost",
        "port": int(DB_PORT) if DB_PORT else 5432,
        "dbname": DB_NAME or "expenses_db",
    }


class ServiceFactory(BaseServiceFactory):
    @classmethod
    def get_service(cls, service_name: str):
        if service_name == "ExpenseResource":
            res = ExpenseResource(config=None)
            res.data_service = cls.get_service("ExpenseDataService")  # type: ignore
            return res
        if service_name == "ExpenseDataService":
            return ExpenseDataService(context=_db_context())
        if service_name == "PlaidDataService":
            return PlaidDataService(context=_db_context())
        if service_name == "ReceiptService":
            ds = cls.get_service("ExpenseDataService")  # type: ignore
            backend = (RECEIPT_STORAGE_BACKEND or "local").lower()
            storage = None
            if backend == "local":
                base = Path(RECEIPT_STORAGE_PATH)
                if not base.is_absolute():
                    base = Path(__file__).resolve().parent.parent.parent / RECEIPT_STORAGE_PATH
                storage = LocalReceiptStorage(base)
            return ReceiptService(data_service=ds, storage=storage, backend=backend)
        return None
