from decimal import ROUND_HALF_UP, Decimal

from app.models import Product

# Order offer shown on the storefront banner: 10% off orders above Rs 5,000.
# The banner text in frontend/index.html (ORDER_OFFER) must match these values.
ORDER_DISCOUNT_THRESHOLD = Decimal("5000.00")
ORDER_DISCOUNT_PERCENT = Decimal("10")

_CENT = Decimal("0.01")


def get_unit_price(product: Product, quantity: int) -> Decimal:
    """Return the price per unit: wholesale from the minimum quantity upward."""
    if quantity >= product.min_wholesale_quantity:
        return Decimal(str(product.wholesale_price))
    return Decimal(str(product.retail_price))


def get_order_discount(subtotal: Decimal) -> Decimal:
    """Return the discount for an order subtotal (0 at or below the threshold)."""
    if subtotal <= ORDER_DISCOUNT_THRESHOLD:
        return Decimal("0.00")
    return (subtotal * ORDER_DISCOUNT_PERCENT / 100).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )
