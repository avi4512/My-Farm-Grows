from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InventoryMovementResponse(BaseModel):
    id: int
    product_id: int | None
    product_name: str
    movement_type: str
    quantity_change: int
    previous_stock: int
    new_stock: int
    reason: str
    order_id: int | None
    changed_by_customer_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryAdjustmentCreate(BaseModel):
    quantity_change: int = Field(
        description="Positive to add stock; negative to remove stock. Must not be zero."
    )
    reason: str = Field(min_length=3, max_length=500)
