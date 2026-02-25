from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Category codes 1-8 align with expense-microservice categories
CATEGORY_NAMES: dict[int, str] = {
    1: "Food",
    2: "Transportation",
    3: "Travel",
    4: "Utilities",
    5: "Entertainment",
    6: "Health",
    7: "Shopping",
    8: "Other",
}

DEFAULT_END_DATE = date(9999, 12, 31)


class BudgetCreate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    amount: Decimal = Field(..., ge=0)
    category_code: int = Field(..., ge=1, le=8)
    start_date: date
    end_date: Optional[date] = None  # default applied in resource


class BudgetUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    amount: Optional[Decimal] = Field(None, ge=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class BudgetResponse(BaseModel):
    budget_id: UUID
    user_id: Optional[int] = None
    name: Optional[str] = None
    category_code: int
    category_name: str
    amount: Decimal
    start_date: date
    end_date: date
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BudgetListParams(BaseModel):
    category_code: Optional[int] = None
    effective_date: Optional[date] = None
    include_inactive: bool = False
    page: int = 1
    page_size: int = 20
