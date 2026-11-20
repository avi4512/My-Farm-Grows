from decimal import Decimal

from fpdf import FPDF

from app.core.config import settings
from app.models.order import Order

# The built-in PDF fonts cannot draw the rupee sign, so amounts use "Rs.".
_PAYMENT_LABELS = {
    "paid": "Paid",
    "pending": "Due",
    "failed": "Not paid",
    "refund_pending": "Refund in progress",
    "refunded": "Refunded",
}

_BRAND = (63, 125, 32)
_MUTED = (110, 110, 110)


def _money(amount: Decimal) -> str:
    sign = "- " if amount < 0 else ""
    return f"{sign}Rs. {abs(amount):,.2f}"


def _payment_line(order: Order) -> str:
    method = "Online" if order.payment_method == "online" else "Cash on delivery"
    status = _PAYMENT_LABELS.get(order.payment_status, order.payment_status)
    if order.payment_method == "cash_on_delivery" and order.payment_status == "pending":
        status = "Due on delivery"
    return f"{method} - {status}"


def _text(value: str) -> str:
    # Core fonts are Latin-1 only; replace anything else instead of failing.
    return value.encode("latin-1", "replace").decode("latin-1")


def _fit(pdf: FPDF, value: str, width: float) -> str:
    """Shorten text with an ellipsis so it stays inside its column."""
    value = _text(value)
    if pdf.get_string_width(value) <= width:
        return value
    while value and pdf.get_string_width(value + "...") > width:
        value = value[:-1]
    return value.rstrip() + "..."


def build_receipt_pdf(order: Order, customer_email: str) -> bytes:
    """Return a one-page order receipt (not a tax invoice) as PDF bytes."""
    pdf = FPDF(format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()
    width = pdf.epw

    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*_BRAND)
    pdf.cell(width / 2, 10, _text(settings.app_name))
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(width / 2, 10, "Order Receipt", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_MUTED)
    for line in (settings.business_address, settings.business_phone):
        if line:
            pdf.cell(0, 5, _text(line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    details = [
        ("Order", f"#{order.id}"),
        ("Date", f"{order.created_at:%d %b %Y}"),
        ("Payment", _payment_line(order)),
    ]
    for label, value in details:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(28, 6, label)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _text(value), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Deliver to", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    address = [
        order.recipient_name,
        order.address_line1,
        order.address_line2,
        order.landmark,
        f"{order.city}, {order.state} {order.postal_code}",
        f"Phone: {order.phone}",
        customer_email,
    ]
    for line in address:
        if line:
            pdf.cell(0, 5, _text(line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    columns = [width * 0.46, width * 0.18, width * 0.18, width * 0.18]
    pdf.set_fill_color(242, 248, 244)
    pdf.set_font("Helvetica", "B", 10)
    for heading, column, align in zip(
        ("Item", "Quantity", "Price", "Amount"), columns, "LRRR", strict=True
    ):
        pdf.cell(column, 8, heading, align=align, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 10)
    subtotal = Decimal("0")
    for item in order.items:
        subtotal += item.subtotal
        row = (
            _fit(pdf, item.product_name, columns[0] - 2),
            f"{item.quantity} {item.unit}",
            _money(item.unit_price),
            _money(item.subtotal),
        )
        for value, column, align in zip(row, columns, "LRRR", strict=True):
            pdf.cell(column, 7, value, align=align, border="B")
        pdf.ln()
    pdf.ln(2)

    totals = [("Subtotal", _money(subtotal))]
    if order.discount_amount:
        totals.append(("Offer discount", _money(-order.discount_amount)))
    delivery = order.delivery_charge
    totals.append(("Delivery", _money(delivery) if delivery else "Free"))
    for label, value in totals:
        pdf.cell(sum(columns[:3]), 6, label, align="R")
        pdf.cell(columns[3], 6, value, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(sum(columns[:3]), 8, "Total", align="R")
    pdf.cell(columns[3], 8, _money(order.total_amount), align="R")
    pdf.ln(14)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(
        0,
        5,
        "This is an order receipt, not a tax invoice. "
        f"Thank you for shopping with {_text(settings.app_name)}.",
    )
    return bytes(pdf.output())
