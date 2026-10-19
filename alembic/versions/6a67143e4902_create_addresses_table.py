"""create addresses table

Revision ID: 6a67143e4902
Revises: d317e89ec1a0
Create Date: 2026-10-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_utils import (
    create_index_if_missing,
    drop_table_if_exists,
    has_table,
)

# revision identifiers, used by Alembic.
revision: str = '6a67143e4902'
down_revision: Union[str, Sequence[str], None] = 'd317e89ec1a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the addresses table if it does not exist."""
    if not has_table('addresses'):
        op.create_table('addresses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('recipient_name', sa.String(length=100), nullable=False),
        sa.Column('phone', sa.String(length=15), nullable=False),
        sa.Column('address_line1', sa.String(length=255), nullable=False),
        sa.Column('address_line2', sa.String(length=255), nullable=True),
        sa.Column('landmark', sa.String(length=150), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('state', sa.String(length=100), nullable=False),
        sa.Column('postal_code', sa.String(length=10), nullable=False),
        sa.Column('country', sa.String(length=100), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
    create_index_if_missing(op.f('ix_addresses_customer_id'), 'addresses', ['customer_id'])
    create_index_if_missing(op.f('ix_addresses_id'), 'addresses', ['id'])


def downgrade() -> None:
    """Drop the addresses table."""
    drop_table_if_exists('addresses')