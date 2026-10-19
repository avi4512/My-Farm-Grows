from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerLogin(BaseModel):
    email: EmailStr
    password: str


class CustomerRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)
    customer_type: Literal["retail", "wholesale"] = "retail"


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    customer_type: str
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
