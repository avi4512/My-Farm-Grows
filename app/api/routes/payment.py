import hashlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings

from app.core.permissions import require_admin
from app.core.security import get_current_customer
from app.db.session import get_db
from app.models.customer import Customer
from app.models.order import Order
from app.models.payment import Payment
from app.models.payment_webhook_event import PaymentWebhookEvent
from app.schemas.payment import (
    PaymentConfigResponse,
    PaymentCreate,
    PaymentResponse,
    PaymentStatusUpdate,
    RazorpayOrderRequest,
    RazorpayOrderResponse,
    RazorpayVerifyRequest,
)
from app.services import razorpay
from app.services.payments import (
    PaymentMismatch,
    check_gateway_payment,
    mark_failed,
    mark_paid,
    mark_refunded,
    refund_paid_online_payment,
)

logger = logging.getLogger("myfarmgrows.payments")

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


# ---- Razorpay ----
# Keep these static routes before the dynamic /{payment_id} routes.


@router.get("/config", response_model=PaymentConfigResponse)
def payment_config():
    """Tell the storefront whether to offer online payment."""
    enabled = settings.online_payments_enabled
    return PaymentConfigResponse(
        online_enabled=enabled, key_id=settings.razorpay_key_id if enabled else None
    )


def _gateway_error(error: razorpay.RazorpayError) -> HTTPException:
    logger.warning("razorpay_error %s", error)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="The payment service is not responding. Please try again shortly.",
    )


@router.post("/razorpay/order", response_model=RazorpayOrderResponse)
def create_razorpay_order(
    payload: RazorpayOrderRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    """Start (or resume) online payment for one of the customer's orders."""
    if not settings.online_payments_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Online payment is not available yet. Please choose cash on delivery."
            ),
        )

    order = (
        db.query(Order)
        .filter(Order.id == payload.order_id, Order.customer_id == customer.id)
        .with_for_update()
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.payment_method != "online":
        raise HTTPException(status_code=400, detail="This order is cash on delivery")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="This order was cancelled")
    if order.payment_status in {"paid", "refunded", "refund_pending"}:
        raise HTTPException(status_code=400, detail="This order is already paid")

    # A Razorpay order accepts retries until one succeeds, so reuse it.
    payment = (
        db.query(Payment)
        .filter(
            Payment.order_id == order.id,
            Payment.status == "pending",
            Payment.gateway_order_id.isnot(None),
            Payment.amount == order.total_amount,
        )
        .order_by(Payment.id.desc())
        .first()
    )
    if payment is None:
        try:
            gateway_order = razorpay.create_order(
                razorpay.to_paise(order.total_amount),
                receipt=f"order_{order.id}",
                notes={"order_id": str(order.id)},
            )
        except razorpay.RazorpayError as error:
            db.rollback()
            raise _gateway_error(error) from error
        payment = Payment(
            order_id=order.id,
            payment_method="online",
            amount=order.total_amount,
            status="pending",
            gateway_order_id=gateway_order["id"],
        )
        db.add(payment)
    if order.payment_status == "failed":
        order.payment_status = "pending"

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return RazorpayOrderResponse(
        key_id=settings.razorpay_key_id,
        razorpay_order_id=payment.gateway_order_id,
        amount=razorpay.to_paise(payment.amount),
        currency="INR",
        order_id=order.id,
        customer_name=customer.name,
        customer_email=customer.email,
    )


def _locked_payment_and_order(db: Session, gateway_order_id: str, customer_id=None):
    query = db.query(Payment).join(Order, Payment.order_id == Order.id)
    query = query.filter(Payment.gateway_order_id == gateway_order_id)
    if customer_id is not None:
        query = query.filter(Order.customer_id == customer_id)
    payment = query.with_for_update(of=Payment).first()
    if payment is None:
        return None, None
    order = db.query(Order).filter(Order.id == payment.order_id).with_for_update().one()
    return payment, order


def _refund_if_cancelled(db: Session, order: Order) -> None:
    """Money that arrives for an order cancelled meanwhile goes straight back."""
    if order.status == "cancelled" and order.payment_status == "paid":
        db.flush()
        refund_paid_online_payment(db, order)


@router.post("/razorpay/verify", response_model=PaymentResponse)
def verify_razorpay_payment(
    payload: RazorpayVerifyRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    """Confirm a payment from Razorpay Checkout before marking the order paid."""
    return _confirm_checkout_payment(
        db,
        payload.razorpay_order_id,
        payload.razorpay_payment_id,
        payload.razorpay_signature,
        customer_id=customer.id,
    )


def _confirm_checkout_payment(
    db: Session,
    gateway_order_id: str,
    gateway_payment_id: str,
    signature: str,
    customer_id=None,
) -> Payment:
    """Check the Checkout signature, then ask Razorpay before marking the order paid."""
    payment, order = _locked_payment_and_order(db, gateway_order_id, customer_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    if not razorpay.payment_signature_is_valid(
        gateway_order_id, gateway_payment_id, signature
    ):
        db.rollback()
        raise HTTPException(status_code=400, detail="Payment could not be verified")

    try:
        # Never trust the browser for amount or status: ask Razorpay.
        entity = razorpay.fetch_payment(gateway_payment_id)
        check_gateway_payment(payment, entity)
        if entity.get("status") == "authorized":
            entity = razorpay.capture_payment(
                gateway_payment_id, razorpay.to_paise(payment.amount)
            )
        if entity.get("status") == "captured":
            mark_paid(db, payment, order, gateway_payment_id)
            _refund_if_cancelled(db, order)
        elif entity.get("status") == "failed":
            mark_failed(db, payment, order, entity.get("error_description"))
        else:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="Payment is not complete yet. Please wait."
            )
        db.commit()
    except PaymentMismatch as error:
        db.rollback()
        logger.warning("payment_mismatch order_id=%s %s", payment.order_id, error)
        raise HTTPException(
            status_code=400, detail="Payment could not be verified"
        ) from error
    except razorpay.RazorpayError as error:
        db.rollback()
        raise _gateway_error(error) from error
    except Exception:
        db.rollback()
        raise

    db.refresh(payment)
    return payment


@router.post("/razorpay/callback", include_in_schema=False)
async def razorpay_callback(request: Request, db: Session = Depends(get_db)):
    """Where Razorpay sends the customer when it cannot use a popup (phones,
    in-app browsers, blocked popups). The tab arrives here without a login,
    so the Checkout signature is what proves the payment."""
    form = await request.form()
    gateway_order_id = str(form.get("razorpay_order_id") or "")
    gateway_payment_id = str(form.get("razorpay_payment_id") or "")
    signature = str(form.get("razorpay_signature") or "")
    if not gateway_order_id:
        # A failed attempt only names its order inside error[metadata].
        try:
            metadata = json.loads(str(form.get("error[metadata]") or "{}"))
        except ValueError:
            metadata = {}
        gateway_order_id = str(metadata.get("order_id") or "")

    result = "failed"
    if gateway_payment_id and signature:
        try:
            payment = _confirm_checkout_payment(
                db, gateway_order_id, gateway_payment_id, signature
            )
            result = "paid" if payment.status == "paid" else "failed"
        except HTTPException as error:
            result = "pending" if error.status_code == 409 else "failed"
    else:
        logger.info(
            "razorpay_callback_failed order=%s reason=%s",
            gateway_order_id,
            form.get("error[description]"),
        )

    payment = (
        db.query(Payment).filter(Payment.gateway_order_id == gateway_order_id).first()
        if gateway_order_id
        else None
    )
    order_part = f"&order={payment.order_id}" if payment else ""
    return RedirectResponse(
        f"/?payment={result}{order_part}#orders",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _record_event(db: Session, event_id: str, event_type: str) -> bool:
    """Store the event id; False if it was handled before."""
    db.add(PaymentWebhookEvent(event_id=event_id[:100], event_type=event_type[:60]))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def _apply_webhook_event(db: Session, event_type: str, payload: dict) -> None:
    if event_type in {"payment.captured", "payment.failed", "order.paid"}:
        entity = (payload.get("payment") or {}).get("entity") or {}
        payment, order = _locked_payment_and_order(db, entity.get("order_id") or "")
        if payment is None:
            return
        check_gateway_payment(payment, entity)
        if event_type == "payment.failed":
            mark_failed(db, payment, order, entity.get("error_description"))
        elif entity.get("status") == "captured":
            mark_paid(db, payment, order, entity.get("id"))
            _refund_if_cancelled(db, order)
    elif event_type in {"refund.processed", "refund.failed"}:
        entity = (payload.get("refund") or {}).get("entity") or {}
        payment_id = entity.get("payment_id")
        if not payment_id:
            return
        payment = (
            db.query(Payment)
            .filter(Payment.transaction_reference == payment_id)
            .with_for_update()
            .first()
        )
        if payment is None:
            return
        order = (
            db.query(Order).filter(Order.id == payment.order_id).with_for_update().one()
        )
        if event_type == "refund.processed":
            mark_refunded(payment, order)
        else:
            # Order stays "refund_pending"; the admin follows up in Razorpay.
            logger.warning("refund_failed order_id=%s", order.id)


@router.post("/razorpay/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Razorpay server-to-server events. Authenticated by signature, not login."""
    body = await request.body()
    if not razorpay.webhook_signature_is_valid(
        body, request.headers.get("X-Razorpay-Signature")
    ):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = json.loads(body)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error
    event_type = str(event.get("event", ""))
    event_id = (
        request.headers.get("X-Razorpay-Event-Id")
        or "body-" + hashlib.sha256(body).hexdigest()
    )

    # A retried delivery hits the unique event id and stops here.
    if not _record_event(db, event_id, event_type):
        return {"status": "duplicate"}

    try:
        _apply_webhook_event(db, event_type, event.get("payload") or {})
        db.commit()
    except PaymentMismatch as error:
        # Nothing changes, but keep the event as handled so Razorpay stops retrying.
        db.rollback()
        logger.warning("webhook_payment_mismatch event=%s %s", event_id, error)
        _record_event(db, event_id, event_type)
        db.commit()
        return {"status": "ignored"}
    except razorpay.RazorpayError as error:
        # Refunding a late payment failed: let Razorpay retry the event.
        db.rollback()
        raise _gateway_error(error) from error
    except Exception:
        db.rollback()
        raise
    return {"status": "ok"}


# Keep static routes before dynamic /{payment_id} routes.
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
        db.query(Payment).order_by(Payment.created_at.desc(), Payment.id.desc()).all()
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
            discrepancies.append(
                {
                    "order_id": order.id,
                    "issue": "order_paid_without_successful_transaction",
                    "order_payment_status": order.payment_status,
                    "successful_transaction_count": successful_count,
                }
            )

        if order.payment_status != "paid" and successful_count > 0:
            discrepancies.append(
                {
                    "order_id": order.id,
                    "issue": "successful_transaction_order_not_paid",
                    "order_payment_status": order.payment_status,
                    "successful_transaction_count": successful_count,
                }
            )

        if successful_count > 1:
            discrepancies.append(
                {
                    "order_id": order.id,
                    "issue": "multiple_successful_transactions",
                    "order_payment_status": order.payment_status,
                    "successful_transaction_count": successful_count,
                }
            )

    return {
        "total_orders_checked": len(orders),
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
    }


# Dynamic routes come after static routes to prevent path conflicts.
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
    payment = db.query(Payment).filter(Payment.id == payment_id).first()

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
        db.query(Payment).filter(Payment.id == payment_id).with_for_update().first()
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
        db.query(Order).filter(Order.id == payment.order_id).with_for_update().first()
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

        # For online payments, call this only after verifying success
        # with the payment provider.
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
