import logging
from html import escape

import httpx
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.customer import Customer
from app.models.order import Order

logger = logging.getLogger("myfarmgrows.email")


async def send_email(to_email: str, subject: str, html: str) -> None:
    if not settings.resend_api_key or not settings.email_from:
        raise RuntimeError(
            "Email delivery is not configured. Set RESEND_API_KEY and EMAIL_FROM."
        )
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.email_from,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
        )
    if response.is_error:
        raise RuntimeError("Email provider rejected the message.")


def otp_email_html(code: str, purpose: str) -> str:
    label = (
        "verify your email address"
        if purpose == "registration"
        else "reset your password"
    )
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#26352b">
      <h2>My Farm Grow</h2>
      <p>Use this one-time password to {label}:</p>
      <div style="font-size:32px;font-weight:700;letter-spacing:8px;padding:16px;background:#f2f8f4;border-radius:8px">{code}</div>
      <p>This code expires in 5 minutes. If you did not request it, you can ignore this email.</p>
    </div>
    """


# Order events that send the customer an email: (subject line, opening line).
_ORDER_STATUS_EMAILS = {
    "shipped": ("has been shipped", "Good news! Your order is on its way."),
    "out_for_delivery": (
        "is out for delivery",
        "Your order is out for delivery and should reach you today.",
    ),
    "delivered": (
        "has been delivered",
        "Your order has been delivered. We hope you enjoy it.",
    ),
    "cancelled": ("has been cancelled", "Your order has been cancelled."),
}


def order_status_email(order: Order, customer_name: str, event: str) -> tuple[str, str]:
    """Return the subject and HTML body for an order status email."""
    headline, opening = _ORDER_STATUS_EMAILS[event]
    lines = [f"<p>Hi {escape(customer_name)},</p>", f"<p>{opening}</p>"]

    delivery = order.delivery
    if delivery is not None and event in ("shipped", "out_for_delivery"):
        details = []
        if delivery.delivery_partner:
            details.append(f"Delivery partner: {escape(delivery.delivery_partner)}")
        if delivery.tracking_number:
            details.append(f"Tracking number: {escape(delivery.tracking_number)}")
        if delivery.estimated_delivery_date and event == "shipped":
            details.append(
                f"Expected delivery: {delivery.estimated_delivery_date:%d %b %Y}"
            )
        if details:
            lines.append("<p>" + "<br>".join(details) + "</p>")

    if event == "cancelled" and order.payment_status in ("refund_pending", "refunded"):
        lines.append(
            f"<p>Your payment of ₹{order.total_amount} will be refunded to your "
            "original payment method. Refunds usually reach your account within "
            "5-7 working days.</p>"
        )

    lines.append(f"<p>Order total: ₹{order.total_amount}</p>")
    lines.append("<p>Thank you for shopping with My Farm Grow.</p>")
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;'
        'color:#26352b"><h2>My Farm Grow</h2>' + "".join(lines) + "</div>"
    )
    return f"Your My Farm Grow order #{order.id} {headline}", html


async def _send_order_status_email(
    to_email: str, subject: str, html: str, order_id: int, event: str
) -> None:
    try:
        await send_email(to_email, subject, html)
    except Exception:
        logger.warning(
            "order_status_email_failed order_id=%s event=%s", order_id, event
        )


def queue_order_status_email(
    background_tasks: BackgroundTasks, db: Session, order: Order, event: str
) -> None:
    """Email the customer about an order status change after the response is sent.

    Call this only after the change is committed. A failed email is logged
    and never affects the order.
    """
    customer = db.get(Customer, order.customer_id)
    if customer is None:
        return
    subject, html = order_status_email(order, customer.name, event)
    background_tasks.add_task(
        _send_order_status_email, customer.email, subject, html, order.id, event
    )
