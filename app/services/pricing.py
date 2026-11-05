from decimal import Decimal

from app.models import Product


def get_unit_price(product: Product, quantity: int) -> Decimal:
    """Return the price per unit: wholesale from the minimum quantity upward."""
    if quantity >= product.min_wholesale_quantity:
        return Decimal(str(product.wholesale_price))
    return Decimal(str(product.retail_price))
