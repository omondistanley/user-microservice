"""Phase 4: Savings goals API models."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    target_amount: Decimal = Field(..., ge=0)
    target_currency: str = Field(default="USD", min_length=3, max_length=3)
    target_date: Optional[date] = None
    start_amount: Decimal = Field(default=Decimal("0"), ge=0)
    household_id: Optional[UUID] = None


class GoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    target_amount: Optional[Decimal] = Field(None, ge=0)
    target_currency: Optional[str] = Field(None, min_length=3, max_length=3)
    target_date: Optional[date] = None
    start_amount: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None


class GoalResponse(BaseModel):
    goal_id: UUID
    user_id: int
    household_id: Optional[UUID] = None
    name: str
    target_amount: Decimal
    target_currency: str
    target_date: Optional[date] = None
    start_amount: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContributionCreate(BaseModel):
    amount: Decimal = Field(..., ge=0)
    contribution_date: date
    source: str = Field(default="manual", pattern="^(manual|auto_cashflow)$")


class ContributionResponse(BaseModel):
    contribution_id: UUID
    goal_id: UUID
    user_id: int
    amount: Decimal
    contribution_date: date
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GoalProgressResponse(BaseModel):
    goal_id: str
    current_amount: float
    target_amount: float
    remaining_amount: float
    percent_complete: float
    days_remaining: Optional[int] = None
    start_amount: float
    contributions_total: float
