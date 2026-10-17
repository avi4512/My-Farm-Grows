
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import require_admin
from app.db.session import get_db
from app.models.customer import Customer
from app.models.order import Order
from app.models import Product
from app.schemas.order import OrderResponse, OrderStatusUpdate


router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
)


@router.get("/test")
def admin_test(
    current_admin: Customer = Depends(require_admin),
):
    return {
        "message": "Admin access granted",
        "admin_id": current_admin.id,
        "role": current_admin.role,
    }


@router.patch(
    "/orders/{order_id}/status",
    response_model=OrderResponse,
)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    # Lock the order to prevent concurrent status changes.
    order = (
        db.query(Order)
        .options(selectinload(Order.items))
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    current_status = order.status
    new_status = payload.status

    # Define permitted status transitions.
    allowed_transitions = {
        "pending": {"processing", "cancelled"},
        "processing": {"shipped", "cancelled"},
        "shipped": {"delivered"},
        "delivered": set(),
        "cancelled": set(),
    }

    # Make repeated requests for the current status idempotent.
    if current_status == new_status:
        return order

    if new_status not in allowed_transitions.get(current_status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot change order status from "
                f"'{current_status}' to '{new_status}'"
            ),
        )

    try:
        # Restore stock only when cancelling an order that has
        # not yet been shipped. Stock was deducted at order creation.
        if new_status == "cancelled":
            quantities_by_product = {}

            for item in order.items:
                quantities_by_product[item.product_id] = (
                    quantities_by_product.get(item.product_id, 0)
                    + item.quantity
                )

            product_ids = sorted(quantities_by_product)

            products = (
                db.query(Product)
                .filter(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update()
                .all()
            )

            products_by_id = {
                product.id: product for product in products
            }

            for product_id, quantity in quantities_by_product.items():
                product = products_by_id.get(product_id)

                if product is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Product ID {product_id} is missing; "
                            "status update could not be completed"
                        ),
                    )

                product.stock_quantity += quantity

        order.status = new_status

        # Payment status is deliberately not changed here.
        # A refund must only be recorded after it is completed.
        db.commit()

        return (
            db.query(Order)
            .options(selectinload(Order.items))
            .filter(Order.id == order_id)
            .first()
        )

    except Exception:
        db.rollback()
        raise
