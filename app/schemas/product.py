
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: Optional[str] = None
    category: str
    unit: str = "kg"
    retail_price: float = Field(gt=0)
    wholesale_price: float = Field(gt=0)
    min_wholesale_quantity: int = Field(default=25, gt=0)
    stock_quantity: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    description: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = Field(default=None, gt=0)
    wholesale_price: Optional[float] = Field(default=None, gt=0)
    min_wholesale_quantity: Optional[int] = Field(default=None, gt=0)
    stock_quantity: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    category: str
    description: Optional[str] = None
    unit: str
    retail_price: float
    wholesale_price: float
    min_wholesale_quantity: int
    stock_quantity: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)