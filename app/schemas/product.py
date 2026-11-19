import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# A product image is either a file served from frontend/images/ or a web URL.
# Anything else (javascript:, data:, ../ paths) is rejected because the value
# is placed into <img src> on the storefront.
_IMAGE_URL = re.compile(
    r"^(https?://[^\s\"'<>]+|images/[\w.-]+\.(jpe?g|png|webp|gif|svg))$", re.I
)


def _clean_image_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _IMAGE_URL.match(value):
        raise ValueError(
            "Image must be an http(s) URL or a file in frontend/images, "
            "for example images/toor-dal.jpg"
        )
    return value


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    category: str = Field(min_length=1, max_length=100)
    unit: str = Field(default="kg", min_length=1, max_length=30)
    retail_price: float = Field(gt=0)
    wholesale_price: float = Field(gt=0)
    min_wholesale_quantity: int = Field(default=25, gt=0)
    stock_quantity: int = Field(default=0, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
    is_active: bool = True

    @field_validator("image_url")
    @classmethod
    def check_image_url(cls, value: str | None) -> str | None:
        return _clean_image_url(value)

    @model_validator(mode="after")
    def wholesale_not_above_retail(self):
        if self.wholesale_price > self.retail_price:
            raise ValueError("Wholesale price cannot be higher than retail price")
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    retail_price: float | None = Field(default=None, gt=0)
    wholesale_price: float | None = Field(default=None, gt=0)
    min_wholesale_quantity: int | None = Field(default=None, gt=0)
    stock_quantity: int | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    @field_validator("image_url")
    @classmethod
    def check_image_url(cls, value: str | None) -> str | None:
        return _clean_image_url(value)


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
    image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)
