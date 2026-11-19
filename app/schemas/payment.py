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


class PaymentConfigResponse(BaseModel):
    online_enabled: bool
    key_id: str | None


class RazorpayOrderRequest(BaseModel):
    order_id: int = Field(gt=0)


class RazorpayOrderResponse(BaseModel):
    """Everything Razorpay Checkout needs in the browser. No secrets."""

    key_id: str
    razorpay_order_id: str
    amount: int  # paise
    currency: str
    order_id: int
    customer_name: str
    customer_email: str


class RazorpayVerifyRequest(BaseModel):
    razorpay_order_id: str = Field(min_length=1, max_length=64)
    razorpay_payment_id: str = Field(min_length=1, max_length=64)
    razorpay_signature: str = Field(min_length=1, max_length=256)


class PaymentStatusUpdate(BaseModel):
    status: Literal["paid", "failed"]
    failure_reason: str | None = None
