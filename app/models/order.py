from __future__ import annotations
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.delivery import Delivery


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    address_id: Mapped[int] = mapped_column(
        ForeignKey("addresses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Snapshot of the delivery address at order time
    recipient_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    phone: Mapped[str] = mapped_column(
        String(15), nullable=False
    )
    address_line1: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    address_line2: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    landmark: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )
    city: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    postal_code: Mapped[str] = mapped_column(
        String(10), nullable=False
    )
    country: Mapped[str] = mapped_column(
        String(100), nullable=False, default="India"
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )

    payment_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="cash_on_delivery"
    )

    payment_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    # A delivery record is created separately by the admin and is optional.
    delivery: Mapped[Delivery | None] = relationship(
    "Delivery",
    uselist=False,
)


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Snapshot of the product details at order time
    product_name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    unit: Mapped[str] = mapped_column(
        String(30), nullable=False
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    order: Mapped["Order"] = relationship(
        back_populates="items"
    )
