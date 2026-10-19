"""create products table

Revision ID: cd866049a0d0
Revises:
Create Date: 2026-10-16
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "cd866049a0d0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the products table if it does not exist."""
    connection = op.get_bind()
    inspector = inspect(connection)

    if "products" not in inspector.get_table_names():
        op.create_table(
            "products",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("unit", sa.String(), nullable=False),
            sa.Column("retail_price", sa.Float(), nullable=False),
            sa.Column("wholesale_price", sa.Float(), nullable=False),
            sa.Column(
                "min_wholesale_quantity",
                sa.Integer(),
                nullable=False,
            ),
            sa.Column("stock_quantity", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
        )


def downgrade() -> None:
    """Remove the products table."""
    # Intentionally do not drop the table automatically.
    # It may contain production or development data.
