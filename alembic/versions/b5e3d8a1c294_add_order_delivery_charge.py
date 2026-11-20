"""add delivery charge to orders

Revision ID: b5e3d8a1c294
Revises: c7e2f9a14d36
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.migration_utils import column_type

revision: str = "b5e3d8a1c294"
down_revision: str | Sequence[str] | None = "c7e2f9a14d36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if column_type("orders", "delivery_charge") is None:
        op.add_column(
            "orders",
            sa.Column(
                "delivery_charge",
                sa.Numeric(12, 2),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    op.drop_column("orders", "delivery_charge")
