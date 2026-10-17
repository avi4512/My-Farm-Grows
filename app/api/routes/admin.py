
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import require_admin
from app.db.session import get_db
from app.models.customer import Customer
from app.models.order import Order
from app.models import Product
from app.schemas.order import OrderResponse, OrderStatusUpdate
from app.schemas.order import (
    OrderResponse,
    OrderStatusUpdate,
    PaymentStatusUpdate,
)
from app.models import InventoryMovement
from app.schemas.inventory import InventoryAdjustmentCreate, InventoryMovementResponse
from app.services.inventory import record_inventory_movement

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


@router.get(
    "/orders",
    response_model=list[OrderResponse],
)
def list_all_orders(
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    """Return all orders for the admin dashboard, newest first."""
    return (
        db.query(Order)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .all()
    )


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

                previous_stock = product.stock_quantity
                product.stock_quantity += quantity
                record_inventory_movement(
                    db,
                    product=product,
                    movement_type="order_cancellation_restock",
                    quantity_change=quantity,
                    previous_stock=previous_stock,
                    new_stock=product.stock_quantity,
                    reason=f"Stock restored after administrator cancelled order #{order.id}",
                    order_id=order.id,
                    changed_by_customer_id=current_admin.id,
                )

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


@router.get(
    "/orders/{order_id}/payment-status",
    response_model=OrderResponse,
)
def get_payment_status(
    order_id: int,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    order = (
        db.query(Order)
        .options(selectinload(Order.items))
        .filter(Order.id == order_id)
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return order


@router.patch(
    "/orders/{order_id}/payment-status",
    response_model=OrderResponse,
)
def update_payment_status(
    order_id: int,
    payload: PaymentStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
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

    current_status = order.payment_status
    new_status = payload.payment_status

    allowed_transitions = {
        "pending": {"paid", "failed"},
        "failed": {"pending"},
        "paid": {"refunded", "partially_refunded"},
        "partially_refunded": {"refunded"},
        "refunded": set(),
    }

    # Repeating the current status is allowed.
    if current_status == new_status:
        return order

    if new_status not in allowed_transitions.get(
        current_status, set()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot change payment status from "
                f"'{current_status}' to '{new_status}'"
            ),
        )

    try:
        order.payment_status = new_status
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


@router.get(
    "/inventory/movements",
    response_model=list[InventoryMovementResponse],
)
def list_inventory_movements(
    product_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    """List stock history, newest first. Admin access required."""
    if skip < 0:
        raise HTTPException(status_code=400, detail="skip must be zero or greater")
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")

    query = db.query(InventoryMovement)
    if product_id is not None:
        query = query.filter(InventoryMovement.product_id == product_id)

    return (
        query.order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post(
    "/products/{product_id}/inventory",
    response_model=InventoryMovementResponse,
    status_code=status.HTTP_201_CREATED,
)
def adjust_product_inventory(
    product_id: int,
    payload: InventoryAdjustmentCreate,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    """Manually add or remove stock, recording the reason and actor."""
    if payload.quantity_change == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quantity_change must not be zero",
        )

    try:
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .with_for_update()
            .first()
        )
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        previous_stock = product.stock_quantity
        new_stock = previous_stock + payload.quantity_change
        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock. Available stock: {previous_stock}",
            )

        product.stock_quantity = new_stock
        movement = record_inventory_movement(
            db,
            product=product,
            movement_type=(
                "stock_in" if payload.quantity_change > 0 else "stock_out"
            ),
            quantity_change=payload.quantity_change,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reason=payload.reason,
            changed_by_customer_id=current_admin.id,
        )
        db.commit()
        db.refresh(movement)
        return movement
    except Exception:
        db.rollback()
        raise
