"""
Receipt create/download/delete with backend branching (local vs db).
"""
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException

from app.services.receipt_storage import (
    RECEIPT_ALLOWED_CONTENT_TYPES,
    RECEIPT_MAX_FILE_BYTES,
    ext_from_content_type,
    sanitize_ext,
)


class ReceiptService:
    def __init__(self, data_service, storage, backend: str):
        self.data_service = data_service
        self.storage = storage  # None when backend == "db"
        self.backend = backend  # "local" or "db"

    def _storage_key(self, user_id: int, expense_id: Optional[str], ext: str) -> str:
        if expense_id:
            return f"users/{user_id}/expenses/{expense_id}/{uuid4()}{ext}"
        return f"users/{user_id}/unmatched/{uuid4()}{ext}"

    def create_receipt(
        self,
        user_id: int,
        file_name: str,
        content_type: str,
        file_size_bytes: int,
        file_bytes: bytes | None = None,
        storage_key: str | None = None,
        expense_id: Optional[str] = None,
    ) -> dict:
        if file_bytes is not None:
            if content_type not in RECEIPT_ALLOWED_CONTENT_TYPES:
                raise HTTPException(status_code=400, detail="Content type not allowed for receipts")
            if len(file_bytes) > RECEIPT_MAX_FILE_BYTES:
                raise HTTPException(status_code=400, detail="File too large")
            if file_size_bytes != len(file_bytes):
                file_size_bytes = len(file_bytes)
            ext = ext_from_content_type(content_type) or sanitize_ext(file_name)
        else:
            ext = ".bin"
        if storage_key is None:
            storage_key = self._storage_key(user_id, expense_id, ext)
        data = {
            "file_name": file_name,
            "content_type": content_type,
            "file_size_bytes": file_size_bytes,
            "storage_key": storage_key,
        }
        if self.backend == "db" and file_bytes is not None:
            data["file_bytes"] = file_bytes
        row = self.data_service.insert_receipt(user_id, data, expense_id=expense_id)
        if self.backend == "local" and file_bytes is not None and self.storage is not None:
            self.storage.save(storage_key, file_bytes)
        return row

    def get_receipt_download(self, receipt_id: str, user_id: int) -> tuple[bytes, str, str]:
        row = self.data_service.get_receipt_by_id(receipt_id, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="Receipt not found")
        content_type = row.get("content_type") or "application/octet-stream"
        file_name = row.get("file_name") or "receipt"
        if self.backend == "db":
            data = self.data_service.get_receipt_bytes(receipt_id, user_id)
            if data is None or len(data) == 0:
                raise HTTPException(status_code=404, detail="Receipt file not found")
            return (data, content_type, file_name)
        if self.storage is None:
            raise HTTPException(status_code=404, detail="Receipt file not found")
        try:
            data = self.storage.get(row["storage_key"])
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Receipt file not found")
        return (data, content_type, file_name)

    def delete_receipt(self, receipt_id: str, user_id: int) -> bool:
        if self.backend == "local" and self.storage is not None:
            row = self.data_service.get_receipt_by_id(receipt_id, user_id)
            if row and row.get("storage_key"):
                try:
                    self.storage.delete(row["storage_key"])
                except Exception:
                    pass
        return self.data_service.delete_receipt(receipt_id, user_id)
