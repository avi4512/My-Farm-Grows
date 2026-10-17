
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


router = APIRouter(prefix="/api/orders", tags=["Orders"])


def get_product_price(product: Product, quantity: int) -> Decimal:
    """Choose price based on the quantity of this product."""
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
    order = (
        db.query(Order)
        .options(selectinload(Order.items))
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
    # Verify that the address belongs to the logged-in customer.
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

    # Retrieve the customer's cart.
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

    # Validate all products and stock before creating the order.
    order_lines = []
    total_amount = Decimal("0.00")

    for cart_item in cart_items:
        product = (
            db.query(Product)
            .filter(Product.id == cart_item.product_id)
            .with_for_update()
            .first()
        )

        if product is None or not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product ID {cart_item.product_id} is unavailable",
            )

        if cart_item.quantity > product.stock_quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient stock for {product.name}. "
                    f"Available stock: {product.stock_quantity}"
                ),
            )

        unit_price = get_product_price(product, cart_item.quantity)
        subtotal = (
            unit_price * cart_item.quantity
        ).quantize(Decimal("0.01"))

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

    try:
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

            # Reserve stock by reducing available stock.
            product.stock_quantity -= quantity

        # Remove cart items only after all order records are prepared.
        db.query(CartItem).filter(
            CartItem.customer_id == customer.id
        ).delete(synchronize_session=False)

        db.commit()

        return get_order_or_404(db, order.id, customer.id)

    except Exception:
        db.rollback()
        raise


@router.get("/", response_model=list[OrderResponse])
def get_my_orders(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    return (
        db.query(Order)
        .options(selectinload(Order.items))
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
    return get_order_or_404(db, order_id, customer.id)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
):
    # Lock the order row so concurrent cancellation requests
    # cannot restore stock more than once.
    order = (
        db.query(Order)
        .options(selectinload(Order.items))
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

    # Customers can cancel only orders that are still pending.
    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Order cannot be cancelled because its "
                f"current status is '{order.status}'"
            ),
        )

    try:
        # Lock products in a consistent order to reduce the
        # possibility of deadlocks.
        quantities_by_product = {}

        for item in order.items:
            quantities_by_product[item.product_id] = (
                quantities_by_product.get(item.product_id, 0)
                + item.quantity
            )

        product_ids = sorted(quantities_by_product)

        products = (
            db.query(Product)
            .filter(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
            .all()
        )

        products_by_id = {product.id: product for product in products}

        # Restore the stock reserved when the order was created.
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

            product.stock_quantity += quantity

        # Change the status in the same transaction as stock restoration.
        order.status = "cancelled"

        # Do not mark a payment as refunded automatically.
        # An actual refund must be completed separately.

        db.commit()

        return get_order_or_404(db, order_id, customer.id)

    except Exception:
        db.rollback()
        raise
