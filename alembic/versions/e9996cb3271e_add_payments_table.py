"""add payments table

Revision ID: e9996cb3271e
Revises: 7b3e5f1c9a20
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
revision: str = "e9996cb3271e"
down_revision: str | Sequence[str] | None = "7b3e5f1c9a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the payments table if it does not exist."""
    if not has_table("payments"):
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("transaction_reference", sa.String(length=150), nullable=True),
            sa.Column("payment_method", sa.String(length=30), nullable=False),
            sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("failure_reason", sa.Text(), nullable=True),
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
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("transaction_reference"),
        )
    create_index_if_missing(op.f("ix_payments_id"), "payments", ["id"])
    create_index_if_missing(op.f("ix_payments_order_id"), "payments", ["order_id"])
    create_index_if_missing(op.f("ix_payments_status"), "payments", ["status"])


def downgrade() -> None:
    """Drop the payments table."""
    drop_table_if_exists("payments")
