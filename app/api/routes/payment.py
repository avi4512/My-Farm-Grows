
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import require_admin
from app.core.security import get_current_customer
from app.db.session import get_db
from app.models.customer import Customer
from app.models.order import Order
from app.models.payment import Payment
from app.schemas.payment import PaymentCreate, PaymentResponse
from sqlalchemy.orm import Session

from app.core.permissions import require_admin
from app.models.customer import Customer
from app.models.order import Order
from app.schemas.payment import PaymentStatusUpdate
from sqlalchemy import func


router = APIRouter(
    prefix="/api/payments",
    tags=["Payments"],
)


@router.post(
    "/",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    order = (
        db.query(Order)
        .filter(
            Order.id == payload.order_id,
            Order.customer_id == customer.id,
        )
        .with_for_update()
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create a payment for a cancelled order",
        )

    if order.payment_status in {"paid", "refunded"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order payment is already completed",
        )

    if order.payment_method != payload.payment_method:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment method does not match the order",
        )

    payment = Payment(
        order_id=order.id,
        payment_method=order.payment_method,
        amount=order.total_amount,
        status="pending",
    )

    try:
        db.add(payment)
        db.commit()
        db.refresh(payment)
        return payment
    except Exception:
        db.rollback()
        raise


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    payment = (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(
            Payment.id == payment_id,
            Order.customer_id == customer.id,
        )
        .first()
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return payment


@router.get(
    "/admin/{payment_id}",
    response_model=PaymentResponse,
)
def get_payment_admin(
    payment_id: int,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .first()
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return payment



@router.patch(
    "/admin/{payment_id}/status",
    response_model=PaymentResponse,
)
def update_payment_transaction_status(
    payment_id: int,
    payload: PaymentStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .with_for_update()
        .first()
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    if payment.status == payload.status:
        return payment

    if payment.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot change payment transaction status "
                f"from '{payment.status}' to '{payload.status}'"
            ),
        )

    order = (
        db.query(Order)
        .filter(Order.id == payment.order_id)
        .with_for_update()
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if payload.status == "paid":
        if order.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot mark payment as paid for a cancelled order",
            )

        if order.payment_status in {"paid", "refunded"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order payment is already completed",
            )

        # For online payments, call this only after
        # verifying success with the payment provider.
        payment.status = "paid"
        payment.failure_reason = None
        order.payment_status = "paid"

    elif payload.status == "failed":
        payment.status = "failed"
        payment.failure_reason = payload.failure_reason

        # Do not overwrite an existing successful payment.
        successful_payment = (
            db.query(Payment.id)
            .filter(
                Payment.order_id == order.id,
                Payment.status == "paid",
                Payment.id != payment.id,
            )
            .first()
        )

        if successful_payment is None:
            order.payment_status = "failed"

    try:
        db.commit()
        db.refresh(payment)
        return payment
    except Exception:
        db.rollback()
        raise


@router.get("/history", response_model=list[PaymentResponse])
def get_payment_history(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    payments = (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(Order.customer_id == customer.id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .all()
    )

    return payments


@router.get(
    "/admin/history",
    response_model=list[PaymentResponse],
)
def get_all_payment_history(
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    payments = (
        db.query(Payment)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .all()
    )

    return payments



@router.get("/admin/reconciliation")
def reconcile_payments(
    db: Session = Depends(get_db),
    current_admin: Customer = Depends(require_admin),
):
    successful_counts = (
        db.query(
            Payment.order_id.label("order_id"),
            func.count(Payment.id).label("successful_count"),
        )
        .filter(Payment.status == "paid")
        .group_by(Payment.order_id)
        .subquery()
    )

    orders = db.query(Order).order_by(Order.id).all()

    discrepancies = []

    for order in orders:
        successful_count = (
            db.query(successful_counts.c.successful_count)
            .filter(successful_counts.c.order_id == order.id)
            .scalar()
            or 0
        )

        if order.payment_status == "paid" and successful_count == 0:
            discrepancies.append({
                "order_id": order.id,
                "issue": "order_paid_without_successful_transaction",
                "order_payment_status": order.payment_status,
                "successful_transaction_count": successful_count,
            })

        if order.payment_status != "paid" and successful_count > 0:
            discrepancies.append({
                "order_id": order.id,
                "issue": "successful_transaction_order_not_paid",
                "order_payment_status": order.payment_status,
                "successful_transaction_count": successful_count,
            })

        if successful_count > 1:
            discrepancies.append({
                "order_id": order.id,
                "issue": "multiple_successful_transactions",
                "order_payment_status": order.payment_status,
                "successful_transaction_count": successful_count,
            })

    return {
        "total_orders_checked": len(orders),
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
    }
