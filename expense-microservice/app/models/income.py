from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

IncomeType = Literal["salary", "freelance", "dividend", "interest", "other"]


class IncomeCreate(BaseModel):
    amount: Decimal = Field(..., ge=0)
    date: date
    currency: str = "USD"
    income_type: IncomeType = "other"
    source_label: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)


class IncomeUpdate(BaseModel):
    amount: Optional[Decimal] = Field(None, ge=0)
    date: Optional[date] = None
    currency: Optional[str] = None
    income_type: Optional[IncomeType] = None
    source_label: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)


class IncomeResponse(BaseModel):
    income_id: UUID
    user_id: int
    amount: Decimal
    date: date
    currency: str
    income_type: IncomeType
    source_label: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncomeSummaryItem(BaseModel):
    group_key: str
    label: str
    total_amount: Decimal
    count: int


class IncomeSummaryResponse(BaseModel):
    group_by: str
    items: list[IncomeSummaryItem]


class CashflowSummaryResponse(BaseModel):
    income_total: Decimal
    expense_total: Decimal
    savings: Decimal
