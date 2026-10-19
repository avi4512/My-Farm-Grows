"""create cart orders and order items

Revision ID: 7b3e5f1c9a20
Revises: 6a67143e4902
Create Date: 2026-10-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.migration_utils import (
    create_index_if_missing,
    drop_table_if_exists,
    has_table,
)

# revision identifiers, used by Alembic.
revision: str = "7b3e5f1c9a20"
down_revision: str | Sequence[str] | None = "6a67143e4902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create cart_items, orders and order_items if they do not exist."""
    if not has_table("cart_items"):
        op.create_table(
            "cart_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"], ["customers.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["product_id"], ["products.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "customer_id", "product_id", name="uq_cart_customer_product"
            ),
        )
    create_index_if_missing(
        op.f("ix_cart_items_customer_id"), "cart_items", ["customer_id"]
    )
    create_index_if_missing(op.f("ix_cart_items_id"), "cart_items", ["id"])
    create_index_if_missing(
        op.f("ix_cart_items_product_id"), "cart_items", ["product_id"]
    )

    if not has_table("orders"):
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("address_id", sa.Integer(), nullable=False),
            sa.Column("recipient_name", sa.String(length=100), nullable=False),
            sa.Column("phone", sa.String(length=15), nullable=False),
            sa.Column("address_line1", sa.String(length=255), nullable=False),
            sa.Column("address_line2", sa.String(length=255), nullable=True),
            sa.Column("landmark", sa.String(length=150), nullable=True),
            sa.Column("city", sa.String(length=100), nullable=False),
            sa.Column("state", sa.String(length=100), nullable=False),
            sa.Column("postal_code", sa.String(length=10), nullable=False),
            sa.Column("country", sa.String(length=100), nullable=False),
            sa.Column(
                "total_amount", sa.Numeric(precision=12, scale=2), nullable=False
            ),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("payment_method", sa.String(length=30), nullable=False),
            sa.Column("payment_status", sa.String(length=30), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["address_id"], ["addresses.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["customer_id"], ["customers.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    create_index_if_missing(op.f("ix_orders_customer_id"), "orders", ["customer_id"])
    create_index_if_missing(op.f("ix_orders_id"), "orders", ["id"])

    if not has_table("order_items"):
        op.create_table(
            "order_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("product_name", sa.String(length=150), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit", sa.String(length=30), nullable=False),
            sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["product_id"], ["products.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    create_index_if_missing(op.f("ix_order_items_id"), "order_items", ["id"])
    create_index_if_missing(
        op.f("ix_order_items_order_id"), "order_items", ["order_id"]
    )
    create_index_if_missing(
        op.f("ix_order_items_product_id"), "order_items", ["product_id"]
    )


def downgrade() -> None:
    """Drop order_items, orders and cart_items."""
    drop_table_if_exists("order_items")
    drop_table_if_exists("orders")
    drop_table_if_exists("cart_items")
