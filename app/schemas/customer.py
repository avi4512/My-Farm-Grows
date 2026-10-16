from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerRegister(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    customer_type: Literal["retail", "wholesale"] = "retail"


class CustomerLogin(BaseModel):
    email: EmailStr
    password: str


class CustomerResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    customer_type: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"