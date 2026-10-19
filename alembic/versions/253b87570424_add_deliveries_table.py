"""add deliveries table

Revision ID: 253b87570424
Revises: c58eaa745b11
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
revision: str = "253b87570424"
down_revision: str | Sequence[str] | None = "c58eaa745b11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the deliveries table if it does not exist."""
    if not has_table("deliveries"):
        op.create_table(
            "deliveries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("tracking_number", sa.String(length=100), nullable=True),
            sa.Column("delivery_partner", sa.String(length=150), nullable=True),
            sa.Column("estimated_delivery_date", sa.Date(), nullable=True),
            sa.Column(
                "status", sa.String(length=30), server_default="pending", nullable=False
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('pending', 'packed', 'shipped', 'out_for_delivery', 'delivered', 'failed', 'returned')",
                name="ck_deliveries_status",
            ),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tracking_number"),
        )
    create_index_if_missing(op.f("ix_deliveries_id"), "deliveries", ["id"])
    create_index_if_missing(
        op.f("ix_deliveries_order_id"), "deliveries", ["order_id"], unique=True
    )


def downgrade() -> None:
    """Drop the deliveries table."""
    drop_table_if_exists("deliveries")
