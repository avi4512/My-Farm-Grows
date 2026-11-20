from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import require_admin
from app.db.session import get_db
from app.models import Delivery, InventoryMovement, Product
from app.models.customer import Customer
from app.models.order import Order
from app.schemas.customer import CustomerAdminResponse, CustomerAdminUpdate
from app.schemas.delivery import (
    DeliveryCreate,
    DeliveryResponse,
    DeliveryUpdate,
)
from app.schemas.inventory import InventoryAdjustmentCreate, InventoryMovementResponse
from app.schemas.order import (
    OrderResponse,
    OrderStatusUpdate,
    PaymentStatusUpdate,
)
from app.services.delivery_sync import sync_order_status_from_delivery
from app.services.email import queue_order_status_email
from app.services.inventory import record_inventory_movement
from app.services.payments import refund_paid_online_payment
from app.services.razorpay import RazorpayError

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
        .options(selectinload(Order.items), selectinload(Order.delivery))
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    # Lock the order to prevent concurrent status changes.
    order = (
        db.query(Order)
        .options(selectinload(Order.items), selectinload(Order.delivery))
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
                f"Cannot change order status from '{current_status}' to '{new_status}'"
            ),
        )

    try:
        # Restore stock only when cancelling an order that has
        # not yet been shipped. Stock was deducted at order creation.
        if new_status == "cancelled":
            quantities_by_product = {}

            for item in order.items:
                quantities_by_product[item.product_id] = (
                    quantities_by_product.get(item.product_id, 0) + item.quantity
                )

            product_ids = sorted(quantities_by_product)

            products = (
                db.query(Product)
                .filter(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update()
                .all()
            )

            products_by_id = {product.id: product for product in products}

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

        # Cancelling a paid online order refunds it through Razorpay. The
        # order is marked refunded only once Razorpay confirms the refund.
        if new_status == "cancelled":
            db.flush()
            try:
                refund_paid_online_payment(db, order)
            except RazorpayError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "The refund could not be started with the payment "
                        "service, so the order was not cancelled. Try again shortly."
                    ),
                ) from error

        db.commit()

        if new_status in ("shipped", "delivered", "cancelled"):
            queue_order_status_email(background_tasks, db, order, new_status)

        return (
            db.query(Order)
            .options(selectinload(Order.items), selectinload(Order.delivery))
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
        .options(selectinload(Order.items), selectinload(Order.delivery))
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
        .options(selectinload(Order.items), selectinload(Order.delivery))
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
        "refund_pending": {"refunded"},
        "refunded": set(),
    }

    # Repeating the current status is allowed.
    if current_status == new_status:
        return order

    if new_status not in allowed_transitions.get(current_status, set()):
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
            .options(selectinload(Order.items), selectinload(Order.delivery))
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
            db.query(Product).filter(Product.id == product_id).with_for_update().first()
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
            movement_type=("stock_in" if payload.quantity_change > 0 else "stock_out"),
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


@router.get(
    "/deliveries",
    response_model=list[DeliveryResponse],
)
def list_deliveries(
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    """List all deliveries, newest first."""
    return (
        db.query(Delivery)
        .order_by(Delivery.created_at.desc(), Delivery.id.desc())
        .all()
    )


@router.post(
    "/deliveries",
    response_model=DeliveryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_delivery(
    payload: DeliveryCreate,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    """Assign delivery details to an existing order."""

    order = (
        db.query(Order).filter(Order.id == payload.order_id).with_for_update().first()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot create a delivery for a cancelled order",
        )

    existing_delivery = (
        db.query(Delivery).filter(Delivery.order_id == payload.order_id).first()
    )

    if existing_delivery is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A delivery already exists for this order",
        )

    # Generate a stable tracking number from the order ID.
    # The Delivery model allows only one delivery per order.
    tracking_number = f"MFG-ORD-{order.id}"

    existing_tracking = (
        db.query(Delivery).filter(Delivery.tracking_number == tracking_number).first()
    )
    if existing_tracking is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Tracking number {tracking_number} already exists. "
                "Please contact support."
            ),
        )

    delivery = Delivery(
        order_id=payload.order_id,
        tracking_number=tracking_number,
        delivery_partner=payload.delivery_partner,
        estimated_delivery_date=payload.estimated_delivery_date,
        status="pending",
    )

    try:
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        return delivery
    except IntegrityError as exc:
        db.rollback()
        # Convert database uniqueness races into a readable API response.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A delivery or tracking number already exists for order "
                f"{payload.order_id}. Please refresh and try again."
            ),
        ) from exc
    except Exception:
        db.rollback()
        raise


@router.patch(
    "/deliveries/{delivery_id}",
    response_model=DeliveryResponse,
)
def update_delivery(
    delivery_id: int,
    payload: DeliveryUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    """Update shipment details and delivery progress.

    When the delivery progress changes, the order status is moved forward
    to match (packed -> processing, shipped / out for delivery -> shipped,
    delivered -> delivered) in the same transaction.
    """

    probe = db.query(Delivery.order_id).filter(Delivery.id == delivery_id).first()

    if probe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )

    # Lock the parent order first, then the delivery, so concurrent order
    # and delivery updates always take locks in the same order.
    order = db.query(Order).filter(Order.id == probe.order_id).with_for_update().first()

    delivery = (
        db.query(Delivery).filter(Delivery.id == delivery_id).with_for_update().first()
    )

    if delivery is None or order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )

    changes = payload.model_dump(exclude_unset=True)

    # Explicit null values are allowed for optional tracking details,
    # but a supplied status cannot be null.
    if "status" in changes and changes["status"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Status cannot be null",
        )

    new_status = changes.get("status")

    # Forward progress may skip intermediate steps (for example, local
    # farm deliveries can go from packed straight to delivered).
    # Delivered and returned are final; failed can be retried.
    allowed_transitions = {
        "pending": {
            "packed",
            "shipped",
            "out_for_delivery",
            "delivered",
            "failed",
        },
        "packed": {
            "shipped",
            "out_for_delivery",
            "delivered",
            "failed",
        },
        "shipped": {
            "out_for_delivery",
            "delivered",
            "failed",
            "returned",
        },
        "out_for_delivery": {"delivered", "failed", "returned"},
        "delivered": set(),
        "failed": {"pending", "packed", "returned"},
        "returned": set(),
    }

    if new_status is not None and new_status != delivery.status:
        if new_status not in allowed_transitions.get(delivery.status, set()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot change delivery status from "
                    f"'{delivery.status}' to '{new_status}'"
                ),
            )

    previous_status = delivery.status

    try:
        for field, value in changes.items():
            setattr(delivery, field, value)

        order_moved = False
        if new_status is not None:
            order_moved = sync_order_status_from_delivery(order, delivery.status)

        db.commit()
        db.refresh(delivery)

        # Out for delivery is its own email. Shipped and delivered are sent
        # only when they move the order, so the customer never gets the same
        # email twice from the order and delivery screens.
        if new_status == "out_for_delivery" and previous_status != new_status:
            queue_order_status_email(background_tasks, db, order, "out_for_delivery")
        elif order_moved and order.status in ("shipped", "delivered"):
            queue_order_status_email(background_tasks, db, order, order.status)

        return delivery

    except Exception:
        db.rollback()
        raise


def _customer_rows(db: Session, query) -> list[CustomerAdminResponse]:
    """Attach each customer's order count to the admin response."""
    order_counts = (
        db.query(Order.customer_id, func.count(Order.id).label("order_count"))
        .group_by(Order.customer_id)
        .subquery()
    )
    rows = (
        query.outerjoin(order_counts, order_counts.c.customer_id == Customer.id)
        .add_columns(func.coalesce(order_counts.c.order_count, 0))
        .all()
    )
    return [
        CustomerAdminResponse.model_validate(customer).model_copy(
            update={
                "order_count": order_count,
                "has_google_login": customer.google_sub is not None,
            }
        )
        for customer, order_count in rows
    ]


@router.get("/customers", response_model=list[CustomerAdminResponse])
def list_customers(
    search: str | None = Query(default=None, max_length=255),
    role: str | None = Query(default=None, pattern="^(customer|admin)$"),
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    """List customer accounts for the admin dashboard, newest first."""
    query = db.query(Customer)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(Customer.name.ilike(term), Customer.email.ilike(term)))
    if role:
        query = query.filter(Customer.role == role)
    return _customer_rows(
        db, query.order_by(Customer.created_at.desc(), Customer.id.desc())
    )


@router.patch("/customers/{customer_id}", response_model=CustomerAdminResponse)
def update_customer(
    customer_id: int,
    payload: CustomerAdminUpdate,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    """Change a customer's role, account type or active flag."""
    customer = (
        db.query(Customer).filter(Customer.id == customer_id).with_for_update().first()
    )
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)

    # An administrator cannot remove their own access. Because the caller stays
    # an active admin, the shop can never be left without one.
    if customer.id == current_admin.id and (
        changes.get("role", "admin") != "admin"
        or changes.get("is_active", True) is False
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "You cannot remove your own admin access or deactivate your own account"
            ),
        )

    for field, value in changes.items():
        setattr(customer, field, value)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _customer_rows(db, db.query(Customer).filter(Customer.id == customer_id))[0]
