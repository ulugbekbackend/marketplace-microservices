"""Public API shapes."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class InitRequest(BaseModel):
    provider: Literal["payme", "click"]


class InitResponse(BaseModel):
    redirect_url: str


class MockPayResponse(BaseModel):
    transaction_id: UUID
    order_id: UUID
    amount_tiyin: int


class PayoutOut(BaseModel):
    id: UUID
    period_start: date
    period_end: date
    gross_tiyin: int
    commission_tiyin: int
    net_tiyin: int
    status: str
    lines_count: int
    created_at: datetime


class PayoutPage(BaseModel):
    items: list[PayoutOut]
    total: int
    page: int
    page_size: int
