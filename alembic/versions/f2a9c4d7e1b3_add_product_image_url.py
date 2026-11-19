"""add image_url to products

Revision ID: f2a9c4d7e1b3
Revises: b82a7f3c1d90
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.migration_utils import column_type

revision: str = "f2a9c4d7e1b3"
down_revision: str | Sequence[str] | None = "b82a7f3c1d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if column_type("products", "image_url") is None:
        op.add_column(
            "products",
            sa.Column("image_url", sa.String(length=500), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("products", "image_url")
