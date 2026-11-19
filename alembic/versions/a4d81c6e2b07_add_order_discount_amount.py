"""add discount_amount to orders

Revision ID: a4d81c6e2b07
Revises: f2a9c4d7e1b3
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.migration_utils import column_type

revision: str = "a4d81c6e2b07"
down_revision: str | Sequence[str] | None = "f2a9c4d7e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing orders had no discount, so they get 0.
    if column_type("orders", "discount_amount") is None:
        op.add_column(
            "orders",
            sa.Column(
                "discount_amount",
                sa.Numeric(12, 2),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    op.drop_column("orders", "discount_amount")
