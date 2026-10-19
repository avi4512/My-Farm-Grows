from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    category: str
    unit: str = "kg"
    retail_price: float = Field(gt=0)
    wholesale_price: float = Field(gt=0)
    min_wholesale_quantity: int = Field(default=25, gt=0)
    stock_quantity: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    category: str | None = None
    unit: str | None = None
    retail_price: float | None = Field(default=None, gt=0)
    wholesale_price: float | None = Field(default=None, gt=0)
    min_wholesale_quantity: int | None = Field(default=None, gt=0)
    stock_quantity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductResponse(BaseModel):
    id: int
    name: str
    category: str
    description: str | None = None
    unit: str
    retail_price: float
    wholesale_price: float
    min_wholesale_quantity: int
    stock_quantity: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
