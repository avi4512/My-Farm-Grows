
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal




class OrderStatusUpdate(BaseModel):
    status: Literal[
        "pending",
        "processing",
        "shipped",
        "delivered",
        "cancelled",
    ]

class OrderCreate(BaseModel):
    address_id: int = Field(gt=0)
    payment_method: str = Field(
        default="cash_on_delivery",
        pattern="^(cash_on_delivery|online)$",
    )


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit: str
    unit_price: Decimal
    subtotal: Decimal

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: int
    customer_id: int
    address_id: int

    recipient_name: str
    phone: str
    address_line1: str
    address_line2: str | None
    landmark: str | None
    city: str
    state: str
    postal_code: str
    country: str

    total_amount: Decimal
    status: str
    payment_method: str
    payment_status: str
    created_at: datetime

    items: list[OrderItemResponse]

    model_config = ConfigDict(from_attributes=True)


class PaymentStatusUpdate(BaseModel):
    payment_status: Literal[
        "pending",
        "paid",
        "failed",
        "refunded",
        "partially_refunded",
    ]