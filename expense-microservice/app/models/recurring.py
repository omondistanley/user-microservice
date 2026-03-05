from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RecurrenceRule = Literal["weekly", "monthly", "yearly"]


class RecurringExpenseCreate(BaseModel):
    amount: Decimal = Field(..., ge=0)
    currency: str = "USD"
    category: Optional[str] = None
    category_code: Optional[int] = None
    description: Optional[str] = Field(None, max_length=2000)
    recurrence_rule: RecurrenceRule
    next_due_date: date
    is_active: bool = True


class RecurringExpenseUpdate(BaseModel):
    amount: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = None
    category: Optional[str] = None
    category_code: Optional[int] = None
    description: Optional[str] = Field(None, max_length=2000)
    recurrence_rule: Optional[RecurrenceRule] = None
    next_due_date: Optional[date] = None
    is_active: Optional[bool] = None


class RecurringExpenseResponse(BaseModel):
    recurring_id: UUID
    user_id: int
    amount: Decimal
    currency: str
    category_code: int
    category_name: str
    description: Optional[str] = None
    recurrence_rule: RecurrenceRule
    next_due_date: date
    last_run_at: Optional[datetime] = None
    last_created_expense_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
