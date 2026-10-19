from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_customer
from app.db.session import get_db
from app.models.address import Address
from app.models.customer import Customer
from app.schemas.address import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
)

router = APIRouter(
    prefix="/api/addresses",
    tags=["Customer Addresses"],
)


def get_owned_address(
    address_id: int,
    customer_id: int,
    db: Session,
) -> Address:
    address = (
        db.query(Address)
        .filter(
            Address.id == address_id,
            Address.customer_id == customer_id,
        )
        .first()
    )

    if address is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found",
        )

    return address


def set_default_address(
    db: Session,
    customer_id: int,
    address_id: int | None = None,
) -> None:
    """Ensure at most one address is marked as default."""
    addresses = db.query(Address).filter(Address.customer_id == customer_id).all()

    for address in addresses:
        address.is_default = address.id == address_id


@router.post(
    "/",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_address(
    address_data: AddressCreate,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    try:
        existing_addresses = (
            db.query(Address).filter(Address.customer_id == current_customer.id).all()
        )

        # Make the first address the default automatically.
        make_default = address_data.is_default or not existing_addresses

        if make_default:
            set_default_address(
                db,
                current_customer.id,
            )

        new_address = Address(
            **address_data.model_dump(exclude={"is_default"}),
            customer_id=current_customer.id,
            is_default=make_default,
        )

        db.add(new_address)
        db.commit()
        db.refresh(new_address)

        return new_address

    except Exception:
        db.rollback()
        raise


@router.get(
    "/",
    response_model=list[AddressResponse],
)
def list_addresses(
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    return (
        db.query(Address)
        .filter(Address.customer_id == current_customer.id)
        .order_by(Address.is_default.desc(), Address.id.desc())
        .all()
    )


@router.get(
    "/{address_id}",
    response_model=AddressResponse,
)
def get_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    return get_owned_address(
        address_id,
        current_customer.id,
        db,
    )


@router.put(
    "/{address_id}",
    response_model=AddressResponse,
)
def update_address(
    address_id: int,
    address_data: AddressUpdate,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    address = get_owned_address(
        address_id,
        current_customer.id,
        db,
    )

    update_data = address_data.model_dump(exclude_unset=True)

    # Prevent explicitly supplied null values for required fields.
    required_fields = {
        "recipient_name",
        "phone",
        "address_line1",
        "city",
        "state",
        "postal_code",
        "country",
        "is_default",
    }

    for field, value in update_data.items():
        if field in required_fields and value is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be null",
            )

    try:
        if update_data.get("is_default") is True:
            set_default_address(
                db,
                current_customer.id,
            )

        for field, value in update_data.items():
            setattr(address, field, value)

        db.commit()
        db.refresh(address)

        return address

    except Exception:
        db.rollback()
        raise


@router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_customer: Customer = Depends(get_current_customer),
):
    address = get_owned_address(
        address_id,
        current_customer.id,
        db,
    )

    was_default = address.is_default
    customer_id = current_customer.id

    try:
        db.delete(address)
        db.flush()

        # If the default address was deleted, promote another address.
        if was_default:
            next_address = (
                db.query(Address)
                .filter(Address.customer_id == customer_id)
                .order_by(Address.id.asc())
                .first()
            )

            if next_address is not None:
                next_address.is_default = True

        db.commit()

    except IntegrityError as exc:
        db.rollback()
        # orders.address_id uses ON DELETE RESTRICT.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This address is used by existing orders and cannot "
                "be deleted. You can edit it instead."
            ),
        ) from exc
    except Exception:
        db.rollback()
        raise
