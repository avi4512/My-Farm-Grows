from fastapi import Depends, HTTPException, status

from app.core.security import get_current_customer
from app.models.customer import Customer


def require_admin(
    current_customer: Customer = Depends(get_current_customer),
) -> Customer:
    if current_customer.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_customer
