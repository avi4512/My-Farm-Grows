from sqlalchemy.orm import Session

from app.models import InventoryMovement, Product


def record_inventory_movement(
    db: Session,
    *,
    product: Product,
    movement_type: str,
    quantity_change: int,
    previous_stock: int,
    new_stock: int,
    reason: str,
    order_id: int | None = None,
    changed_by_customer_id: int | None = None,
) -> InventoryMovement:
    """Add an inventory audit row to the current DB transaction."""
    movement = InventoryMovement(
        product_id=product.id,
        product_name=product.name,
        movement_type=movement_type,
        quantity_change=quantity_change,
        previous_stock=previous_stock,
        new_stock=new_stock,
        reason=reason,
        order_id=order_id,
        changed_by_customer_id=changed_by_customer_id,
    )
    db.add(movement)
    return movement
