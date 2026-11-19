"""add Razorpay payment fields and webhook event log

Revision ID: c7e2f9a14d36
Revises: a4d81c6e2b07
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.migration_utils import column_type, has_table

revision: str = "c7e2f9a14d36"
down_revision: str | Sequence[str] | None = "a4d81c6e2b07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if column_type("payments", "gateway_order_id") is None:
        op.add_column(
            "payments",
            sa.Column("gateway_order_id", sa.String(length=64), nullable=True),
        )
        op.create_unique_constraint(
            "uq_payments_gateway_order_id", "payments", ["gateway_order_id"]
        )
    if column_type("payments", "gateway_refund_id") is None:
        op.add_column(
            "payments",
            sa.Column("gateway_refund_id", sa.String(length=64), nullable=True),
        )
    if not has_table("payment_webhook_events"):
        op.create_table(
            "payment_webhook_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.String(length=100), nullable=False, unique=True),
            sa.Column("event_type", sa.String(length=60), nullable=False),
            sa.Column(
                "received_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_table("payment_webhook_events")
    op.drop_column("payments", "gateway_refund_id")
    op.drop_constraint("uq_payments_gateway_order_id", "payments", type_="unique")
    op.drop_column("payments", "gateway_order_id")
