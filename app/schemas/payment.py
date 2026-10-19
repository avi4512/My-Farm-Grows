from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    order_id: int = Field(gt=0)
    payment_method: Literal["cash_on_delivery", "online"]


class PaymentResponse(BaseModel):
    id: int
    order_id: int
    transaction_reference: str | None
    payment_method: str
    amount: Decimal
    status: str
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentStatusUpdate(BaseModel):
    status: Literal["paid", "failed"]
    failure_reason: str | None = None
