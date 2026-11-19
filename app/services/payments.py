"""Payment state changes shared by checkout verification, the webhook and refunds.

Every function here expects the caller to have locked the payment and order
rows (SELECT ... FOR UPDATE) and to commit afterwards. Each one is safe to
call twice: a retried webhook or a double-submitted checkout changes nothing.
"""

import logging

from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.payment import Payment
from app.services import razorpay

logger = logging.getLogger("myfarmgrows.payments")


class PaymentMismatch(Exception):
    """The gateway payment does not belong to this order or has the wrong amount."""


def check_gateway_payment(payment: Payment, entity: dict) -> None:
    """Make sure a Razorpay payment entity really pays for this Payment row."""
    if entity.get("order_id") != payment.gateway_order_id:
        raise PaymentMismatch("Payment belongs to a different Razorpay order")
    if entity.get("currency") != "INR":
        raise PaymentMismatch("Payment currency is not INR")
    if int(entity.get("amount", -1)) != razorpay.to_paise(payment.amount):
        raise PaymentMismatch("Payment amount does not match the order total")


def _other_paid_payment_exists(db: Session, payment: Payment) -> bool:
    return (
        db.query(Payment.id)
        .filter(
            Payment.order_id == payment.order_id,
            Payment.status == "paid",
            Payment.id != payment.id,
        )
        .first()
        is not None
    )


def mark_paid(db: Session, payment: Payment, order: Order, gateway_payment_id: str):
    if payment.status in {"paid", "refunded"}:
        return
    payment.status = "paid"
    payment.transaction_reference = gateway_payment_id
    payment.failure_reason = None
    if order.payment_status not in {"refunded", "refund_pending"}:
        order.payment_status = "paid"
    if _other_paid_payment_exists(db, payment):
        # Two attempts both went through. Reconciliation shows it; refund one.
        logger.warning("double_payment order_id=%s", order.id)


def mark_failed(db: Session, payment: Payment, order: Order, reason: str | None):
    if payment.status != "pending":
        return
    payment.status = "failed"
    payment.failure_reason = (reason or "Payment failed")[:500]
    if order.payment_status == "pending" and not _other_paid_payment_exists(
        db, payment
    ):
        order.payment_status = "failed"


def mark_refunded(payment: Payment, order: Order):
    if payment.status == "refunded":
        return
    payment.status = "refunded"
    order.payment_status = "refunded"


def refund_paid_online_payment(db: Session, order: Order) -> str | None:
    """Refund a cancelled order's online payment in full through Razorpay.

    Returns "refunded", "refund_pending", or None when there is nothing to
    refund. Raises razorpay.RazorpayError if Razorpay refuses, so the caller
    can roll back the cancellation instead of keeping the customer's money.
    """
    payment = (
        db.query(Payment)
        .filter(
            Payment.order_id == order.id,
            Payment.payment_method == "online",
            Payment.status == "paid",
            Payment.transaction_reference.isnot(None),
            Payment.gateway_order_id.isnot(None),
        )
        .with_for_update()
        .first()
    )
    if payment is None:
        return None
    if payment.gateway_refund_id:
        return order.payment_status

    refund = razorpay.refund_payment(
        payment.transaction_reference,
        razorpay.to_paise(payment.amount),
        receipt=f"refund_order_{order.id}",
    )
    payment.gateway_refund_id = refund.get("id")
    if refund.get("status") == "processed":
        mark_refunded(payment, order)
        return "refunded"
    # Razorpay finishes most refunds later; refund.processed (webhook) completes it.
    order.payment_status = "refund_pending"
    return "refund_pending"
