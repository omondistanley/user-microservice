from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HoldingCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    quantity: Decimal = Field(..., gt=0)
    avg_cost: Decimal = Field(..., ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    exchange: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = Field(None, max_length=512)
    household_id: Optional[UUID] = None
    account_type: Optional[str] = Field(default="taxable", max_length=32)
    role_label: Optional[str] = Field(None, max_length=32)


class HoldingUpdate(BaseModel):
    quantity: Optional[Decimal] = Field(None, gt=0)
    avg_cost: Optional[Decimal] = Field(None, ge=0)
    exchange: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = Field(None, max_length=512)
    account_type: Optional[str] = Field(None, max_length=32)
    role_label: Optional[str] = Field(None, max_length=32)


class HoldingResponse(BaseModel):
    holding_id: UUID
    user_id: int
    household_id: Optional[UUID] = None
    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    currency: str
    exchange: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    external_id: Optional[str] = None
    account_type: Optional[str] = None
    role_label: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HoldingListParams(BaseModel):
    household_id: Optional[UUID] = None
    symbol: Optional[str] = None
    page: int = 1
    page_size: int = 50
