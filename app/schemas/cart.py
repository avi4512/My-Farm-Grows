from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CartItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(default=1, gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)


class CartItemResponse(BaseModel):
    id: int
    customer_id: int
    product_id: int
    quantity: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CartLineResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class CartResponse(BaseModel):
    items: list[CartLineResponse]
    total: Decimal
