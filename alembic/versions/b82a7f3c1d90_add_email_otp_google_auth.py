"""add verified email, Google identity and email OTP challenges

Revision ID: b82a7f3c1d90
Revises: 9d4c1a6e2f58
Create Date: 2026-10-31
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b82a7f3c1d90"
down_revision: str | Sequence[str] | None = "9d4c1a6e2f58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("customers", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.create_index("ix_customers_google_sub", "customers", ["google_sub"], unique=True)
    # Existing accounts are retained and treated as verified to avoid locking out
    # customers who registered before email verification was introduced.
    op.alter_column("customers", "email_verified", server_default=sa.false())

    op.create_table(
        "email_otps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("pending_name", sa.String(length=100), nullable=True),
        sa.Column("customer_type", sa.String(length=20), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_otps_email", "email_otps", ["email"])
    op.create_index("ix_email_otps_purpose", "email_otps", ["purpose"])


def downgrade() -> None:
    op.drop_index("ix_email_otps_purpose", table_name="email_otps")
    op.drop_index("ix_email_otps_email", table_name="email_otps")
    op.drop_table("email_otps")
    op.drop_index("ix_customers_google_sub", table_name="customers")
    op.drop_column("customers", "google_sub")
    op.drop_column("customers", "email_verified")
