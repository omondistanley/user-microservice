from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(..., ge=0)
    date: date
    category: Optional[str] = None
    category_code: Optional[int] = None
    currency: str = "USD"
    budget_category_id: Optional[str] = None
    description: Optional[str] = Field(None, max_length=2000)


class ExpenseUpdate(BaseModel):
    amount: Optional[Decimal] = Field(None, ge=0)
    date: Optional[date] = None
    category: Optional[str] = None
    category_code: Optional[int] = None
    currency: Optional[str] = None
    budget_category_id: Optional[str] = None
    description: Optional[str] = Field(None, max_length=2000)


class ExpenseResponse(BaseModel):
    expense_id: UUID
    user_id: int
    category_code: int
    category_name: str
    amount: Decimal
    date: date
    currency: str
    budget_category_id: Optional[str] = None
    description: Optional[str] = None
    balance_after: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime
    source: Optional[str] = None
    plaid_transaction_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExpenseListParams(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    category_code: Optional[int] = None
    category: Optional[str] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    page: int = 1
    page_size: int = 20


class BalanceResponse(BaseModel):
    balance_after: Decimal


class BalanceHistoryItem(BaseModel):
    date: str
    balance: Decimal


class BalanceHistoryResponse(BaseModel):
    items: list[BalanceHistoryItem]


class SummaryItem(BaseModel):
    group_key: str
    label: str
    total_amount: Decimal
    count: int


class SummaryResponse(BaseModel):
    group_by: str
    items: list[SummaryItem]
