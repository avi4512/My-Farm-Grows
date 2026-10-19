"""add inventory movement history

Revision ID: c58eaa745b11
Revises: e9996cb3271e
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
revision: str = 'c58eaa745b11'
down_revision: Union[str, Sequence[str], None] = 'e9996cb3271e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the inventory_movements table if it does not exist."""
    if not has_table('inventory_movements'):
        op.create_table('inventory_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('product_name', sa.String(length=150), nullable=False),
        sa.Column('movement_type', sa.String(length=40), nullable=False),
        sa.Column('quantity_change', sa.Integer(), nullable=False),
        sa.Column('previous_stock', sa.Integer(), nullable=False),
        sa.Column('new_stock', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('changed_by_customer_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['changed_by_customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
        )
    create_index_if_missing(op.f('ix_inventory_movements_changed_by_customer_id'), 'inventory_movements', ['changed_by_customer_id'])
    create_index_if_missing(op.f('ix_inventory_movements_created_at'), 'inventory_movements', ['created_at'])
    create_index_if_missing(op.f('ix_inventory_movements_id'), 'inventory_movements', ['id'])
    create_index_if_missing(op.f('ix_inventory_movements_movement_type'), 'inventory_movements', ['movement_type'])
    create_index_if_missing(op.f('ix_inventory_movements_order_id'), 'inventory_movements', ['order_id'])
    create_index_if_missing(op.f('ix_inventory_movements_product_id'), 'inventory_movements', ['product_id'])


def downgrade() -> None:
    """Drop the inventory_movements table."""
    drop_table_if_exists('inventory_movements')