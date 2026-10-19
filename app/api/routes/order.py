from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.security import get_current_customer
from app.db.session import get_db
from app.models import Product
from app.models.address import Address
from app.models.cart import CartItem
from app.models.customer import Customer
from app.models.order import Order, OrderItem
from app.schemas.order import OrderCreate, OrderResponse
from app.services.inventory import record_inventory_movement

router = APIRouter(prefix="/api/orders", tags=["Orders"])


def get_product_price(product: Product, quantity: int) -> Decimal:
    """Choose the product price based on the ordered quantity."""
    if quantity >= product.min_wholesale_quantity:
        price = product.wholesale_price
    else:
        price = product.retail_price

    return Decimal(str(price))


def get_order_or_404(
    db: Session,
    order_id: int,
    customer_id: int,
) -> Order:
    """Return an order belonging to the specified customer."""
    order = (
        db.query(Order)
        .options(selectinload(Order.items), selectinload(Order.delivery))
        .filter(
            Order.id == order_id,
            Order.customer_id == customer_id,
        )
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return order


@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    """
    Create an order, deduct stock, and clear the customer's cart
    in one database transaction.
    """
    try:
        # 1. Verify that the delivery address belongs to the customer.
        address = (
            db.query(Address)
            .filter(
                Address.id == payload.address_id,
                Address.customer_id == customer.id,
            )
            .first()
        )

        if address is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Delivery address not found",
            )

        # 2. Lock the customer's cart rows.
        cart_items = (
            db.query(CartItem)
            .filter(CartItem.customer_id == customer.id)
            .order_by(CartItem.id)
            .with_for_update()
            .all()
        )

        if not cart_items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your cart is empty",
            )

        # 3. Collect unique product IDs and lock products in a
        # consistent order to reduce the risk of deadlocks.
        product_ids = sorted({item.product_id for item in cart_items})

        products = (
            db.query(Product)
            .filter(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
            .all()
        )

        products_by_id = {product.id: product for product in products}

        # 4. Validate every product and available stock before
        # creating the order or deducting any stock.
        order_lines = []
        total_amount = Decimal("0.00")

        for cart_item in cart_items:
            product = products_by_id.get(cart_item.product_id)

            if product is None or not product.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(f"Product ID {cart_item.product_id} is unavailable"),
                )

            if cart_item.quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(f"Invalid quantity for product {product.name}"),
                )

            if cart_item.quantity > product.stock_quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Insufficient stock for {product.name}. "
                        f"Available stock: {product.stock_quantity}"
                    ),
                )

            unit_price = get_product_price(
                product,
                cart_item.quantity,
            )

            subtotal = (unit_price * cart_item.quantity).quantize(Decimal("0.01"))

            total_amount += subtotal

            order_lines.append(
                {
                    "product": product,
                    "quantity": cart_item.quantity,
                    "unit_price": unit_price,
                    "subtotal": subtotal,
                }
            )

        total_amount = total_amount.quantize(Decimal("0.01"))

        # 5. Create the order and persist its ID inside the transaction.
        order = Order(
            customer_id=customer.id,
            address_id=address.id,
            recipient_name=address.recipient_name,
            phone=address.phone,
            address_line1=address.address_line1,
            address_line2=address.address_line2,
            landmark=address.landmark,
            city=address.city,
            state=address.state,
            postal_code=address.postal_code,
            country=address.country,
            total_amount=total_amount,
            status="pending",
            payment_method=payload.payment_method,
            payment_status="pending",
        )

        db.add(order)
        db.flush()

        # 6. Create order items and deduct stock.
        # Product rows remain locked until commit or rollback.
        for line in order_lines:
            product = line["product"]
            quantity = line["quantity"]

            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit=product.unit,
                unit_price=line["unit_price"],
                subtotal=line["subtotal"],
            )

            db.add(order_item)

            previous_stock = product.stock_quantity
            product.stock_quantity -= quantity
            record_inventory_movement(
                db,
                product=product,
                movement_type="order_deduction",
                quantity_change=-quantity,
                previous_stock=previous_stock,
                new_stock=product.stock_quantity,
                reason=f"Stock deducted for order #{order.id}",
                order_id=order.id,
                changed_by_customer_id=customer.id,
            )

        # 7. Clear the cart only after all order items are prepared.
        db.query(CartItem).filter(CartItem.customer_id == customer.id).delete(
            synchronize_session=False
        )

        # 8. Commit order creation, stock deduction, and cart clearing
        # together. Any failure before commit rolls back the transaction.
        db.commit()

        # Save the ID before loading the response.
        order_id = order.id

        return get_order_or_404(
            db,
            order_id,
            customer.id,
        )

    except Exception:
        db.rollback()
        raise


@router.get("/", response_model=list[OrderResponse])
def get_my_orders(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    """Return the logged-in customer's orders."""
    return (
        db.query(Order)
        .options(selectinload(Order.items), selectinload(Order.delivery))
        .filter(Order.customer_id == customer.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    """Return one order belonging to the logged-in customer."""
    return get_order_or_404(
        db,
        order_id,
        customer.id,
    )


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    """
    Cancel a pending order and restore its stock exactly once,
    within the same transaction as the status change.
    """
    try:
        # 1. Lock the customer's order to prevent concurrent
        # cancellation requests from restoring stock twice.
        order = (
            db.query(Order)
            .options(selectinload(Order.items), selectinload(Order.delivery))
            .filter(
                Order.id == order_id,
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

        # Customers can cancel pending orders only.
        if order.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Order cannot be cancelled because its "
                    f"current status is '{order.status}'"
                ),
            )

        # 2. Aggregate quantities by product.
        quantities_by_product = {}

        for item in order.items:
            quantities_by_product[item.product_id] = (
                quantities_by_product.get(item.product_id, 0) + item.quantity
            )

        # 3. Lock products in ascending ID order.
        product_ids = sorted(quantities_by_product)

        products = (
            db.query(Product)
            .filter(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
            .all()
        )

        products_by_id = {product.id: product for product in products}

        # 4. Restore the reserved stock.
        for product_id, quantity in quantities_by_product.items():
            product = products_by_id.get(product_id)

            if product is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Product ID {product_id} is missing; "
                        "order cancellation could not be completed"
                    ),
                )

            previous_stock = product.stock_quantity
            product.stock_quantity += quantity
            record_inventory_movement(
                db,
                product=product,
                movement_type="order_cancellation_restock",
                quantity_change=quantity,
                previous_stock=previous_stock,
                new_stock=product.stock_quantity,
                reason=f"Stock restored after customer cancelled order #{order.id}",
                order_id=order.id,
                changed_by_customer_id=customer.id,
            )

        # 5. Update status in the same transaction as restocking.
        order.status = "cancelled"
        cancelled_order_id = order.id

        # Do not automatically mark a payment as refunded.
        db.commit()

        return get_order_or_404(
            db,
            cancelled_order_id,
            customer.id,
        )

    except Exception:
        db.rollback()
        raise
