from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReceiptCreate(BaseModel):
    file_name: str
    content_type: str
    file_size_bytes: int
    storage_key: str


class ReceiptResponse(BaseModel):
    receipt_id: UUID
    expense_id: UUID
    user_id: int
    file_name: str
    content_type: str
    file_size_bytes: int
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)
