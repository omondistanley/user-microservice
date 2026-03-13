from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Quote(BaseModel):
    symbol: str
    price: Decimal
    currency: str = "USD"
    as_of: datetime
    provider: str
    stale_seconds: int = Field(ge=0)


class Bar(BaseModel):
    symbol: str
    interval: str
    period_start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    provider: str


class ProviderStatus(BaseModel):
    provider: str
    status: Literal["healthy", "degraded", "down"]
    latency_ms: Optional[float] = None
    error_rate: Optional[float] = None
    last_checked_at: Optional[datetime] = None

