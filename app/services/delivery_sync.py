from app.models.order import Order

# Order statuses in the order they normally progress.
# "cancelled" is deliberately absent: cancelled orders are never changed.
_ORDER_RANK = {
    "pending": 0,
    "processing": 1,
    "shipped": 2,
    "delivered": 3,
}

# The order status implied by each delivery status.
# failed / returned / pending imply nothing: an admin decides what to do.
_ORDER_STATUS_FOR_DELIVERY = {
    "packed": "processing",
    "shipped": "shipped",
    "out_for_delivery": "shipped",
    "delivered": "delivered",
}


def sync_order_status_from_delivery(order: Order, delivery_status: str) -> bool:
    """Move the order status forward to match its delivery progress.

    The order status only ever moves forward, and cancelled orders are left
    untouched. Payment status and stock are never changed here.

    Returns True if the order status was changed. The caller owns the
    transaction and must commit.
    """
    target = _ORDER_STATUS_FOR_DELIVERY.get(delivery_status)
    if target is None:
        return False

    current_rank = _ORDER_RANK.get(order.status)
    if current_rank is None:  # cancelled or an unknown status
        return False

    if _ORDER_RANK[target] <= current_rank:
        return False

    order.status = target
    return True