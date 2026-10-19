from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_customer
from app.db.session import get_db
from app.models.customer import Customer
from app.schemas.customer import (
    CustomerRegister,
    CustomerResponse,
    TokenResponse,
)
from app.services.auth import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_customer(
    customer_data: CustomerRegister,
    db: Session = Depends(get_db),
):
    email = str(customer_data.email).lower()

    existing_customer = db.scalar(select(Customer).where(Customer.email == email))

    if existing_customer:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    customer = Customer(
        name=customer_data.name,
        email=email,
        hashed_password=hash_password(customer_data.password),
        customer_type=customer_data.customer_type,
        role="customer",
        is_active=True,
    )

    db.add(customer)

    try:
        db.commit()
        db.refresh(customer)
    except Exception:
        db.rollback()
        raise

    return customer


@router.post("/login", response_model=TokenResponse)
def login_customer(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form_data.username.lower()

    customer = db.scalar(select(Customer).where(Customer.email == email))

    if customer is None or not verify_password(
        form_data.password,
        customer.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive",
        )

    return TokenResponse(access_token=create_access_token(customer.id))


@router.get("/me", response_model=CustomerResponse)
def get_my_profile(
    current_customer: Customer = Depends(get_current_customer),
):
    return current_customer
