from decimal import ROUND_HALF_UP, Decimal

from app.models import Product

# Order offer shown on the storefront banner: 10% off orders above Rs 5,000.
# The banner text in frontend/index.html and ORDER_OFFER in frontend/js/shop.js
# must match these values.
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


# Delivery is offered in these states only. It is free above the threshold,
# measured on the goods total after the offer discount.
# DELIVERY in frontend/js/shop.js must match these values.
DELIVERY_CHARGES = {
    "andhra pradesh": Decimal("50.00"),
    "telangana": Decimal("150.00"),
}
FREE_DELIVERY_THRESHOLD = Decimal("2000.00")

# Short forms and a common misspelling customers type for the state.
_STATE_ALIASES = {
    "ap": "andhra pradesh",
    "ts": "telangana",
    "tg": "telangana",
    "telengana": "telangana",
}


def normalize_state(state: str) -> str:
    key = " ".join(state.replace(".", "").lower().split())
    return _STATE_ALIASES.get(key, key)


def get_delivery_charge(state: str, goods_total: Decimal) -> Decimal | None:
    """Return the delivery charge for a state, or None if it is not served."""
    charge = DELIVERY_CHARGES.get(normalize_state(state))
    if charge is None:
        return None
    if goods_total > FREE_DELIVERY_THRESHOLD:
        return Decimal("0.00")
    return charge
