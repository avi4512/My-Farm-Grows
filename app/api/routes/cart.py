from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_customer
from app.db.session import get_db
from app.models import Product
from app.models.cart import CartItem
from app.models.customer import Customer
from app.schemas.cart import (
    CartItemCreate,
    CartItemUpdate,
    CartLineResponse,
    CartResponse,
)

router = APIRouter(prefix="/api/cart", tags=["Shopping Cart"])


def get_product_price(product: Product, customer: Customer) -> Decimal:
    """Choose the price according to the customer's account type."""
    if customer.customer_type == "wholesale":
        price = product.wholesale_price
    else:
        price = product.retail_price

    if price is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Price is not configured for this customer type",
        )

    return Decimal(str(price))


def get_cart_item(
    db: Session,
    item_id: int,
    customer_id: int,
) -> CartItem:
    item = (
        db.query(CartItem)
        .filter(
            CartItem.id == item_id,
            CartItem.customer_id == customer_id,
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )

    return item


def build_cart_response(
    db: Session,
    customer: Customer,
) -> CartResponse:
    items = (
        db.query(CartItem)
        .filter(CartItem.customer_id == customer.id)
        .order_by(CartItem.id)
        .all()
    )

    lines = []
    total = Decimal("0.00")

    for item in items:
        product = db.get(Product, item.product_id)

        # Skip products that are no longer available.
        if product is None or not product.is_active:
            continue

        unit_price = get_product_price(product, customer)
        subtotal = unit_price * item.quantity
        total += subtotal

        lines.append(
            CartLineResponse(
                id=item.id,
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=unit_price,
                subtotal=subtotal,
            )
        )

    return CartResponse(items=lines, total=total)


@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
)
def add_to_cart(
    payload: CartItemCreate,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    product = db.get(Product, payload.product_id)

    if product is None or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or unavailable",
        )

    # Validate that the customer's account has a configured price.
    get_product_price(product, customer)

    item = (
        db.query(CartItem)
        .filter(
            CartItem.customer_id == customer.id,
            CartItem.product_id == payload.product_id,
        )
        .first()
    )

    if item:
        item.quantity += payload.quantity
    else:
        item = CartItem(
            customer_id=customer.id,
            product_id=payload.product_id,
            quantity=payload.quantity,
        )
        db.add(item)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return build_cart_response(db, customer)


@router.get("", response_model=CartResponse)
def get_cart(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    return build_cart_response(db, customer)


@router.patch("/items/{item_id}", response_model=CartResponse)
def update_cart_item(
    item_id: int,
    payload: CartItemUpdate,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    item = get_cart_item(db, item_id, customer.id)

    product = db.get(Product, item.product_id)

    if product is None or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product is no longer available",
        )

    get_product_price(product, customer)

    item.quantity = payload.quantity

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return build_cart_response(db, customer)


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_cart_item(
    item_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    item = get_cart_item(db, item_id, customer.id)

    db.delete(item)
    db.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    db.query(CartItem).filter(CartItem.customer_id == customer.id).delete(
        synchronize_session=False
    )

    db.commit()
