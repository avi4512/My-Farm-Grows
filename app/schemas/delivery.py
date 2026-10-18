
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DeliveryStatus = Literal[
    "pending",
    "packed",
    "shipped",
    "out_for_delivery",
    "delivered",
    "failed",
    "returned",
]


class DeliveryCreate(BaseModel):
    order_id: int = Field(gt=0)
    tracking_number: str | None = Field(default=None, max_length=100)
    delivery_partner: str | None = Field(default=None, max_length=150)
    estimated_delivery_date: date | None = None


class DeliveryUpdate(BaseModel):
    tracking_number: str | None = Field(default=None, max_length=100)
    delivery_partner: str | None = Field(default=None, max_length=150)
    estimated_delivery_date: date | None = None
    status: DeliveryStatus | None = None


class DeliveryResponse(BaseModel):
    id: int
    order_id: int
    tracking_number: str | None
    delivery_partner: str | None
    estimated_delivery_date: date | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
