from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.customer import Customer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

JWT_SECRET_KEY = settings.jwt_secret_key
JWT_ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


def create_access_token(customer_id: int) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(customer_id),
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        return payload

    except InvalidTokenError:
        return {}


def get_current_customer(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Customer:
    payload = decode_access_token(token)

    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        customer_id = int(payload["sub"])
    except TypeError, ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    customer = db.query(Customer).filter(Customer.id == customer_id).first()

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return customer
