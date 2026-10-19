"""align products table with the Product model

Money columns were created as FLOAT and description as VARCHAR, while the
model defines NUMERIC(10, 2) and TEXT. Also adds the indexes declared on
the model, and re-creates cart_items if an earlier, faulty migration
dropped it from an existing database.

Revision ID: 9d4c1a6e2f58
Revises: 253b87570424
Create Date: 2026-10-18 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.migration_utils import (
    column_type,
    create_index_if_missing,
    has_table,
)

# revision identifiers, used by Alembic.
revision: str = '9d4c1a6e2f58'
down_revision: Union[str, Sequence[str], None] = '253b87570424'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_money_numeric(col_type) -> bool:
    # sa.Float is a subclass of sa.Numeric, so exclude it explicitly.
    return (
        isinstance(col_type, sa.Numeric)
        and not isinstance(col_type, sa.Float)
        and getattr(col_type, 'scale', None) == 2
    )


def upgrade() -> None:
    """Align products and make sure cart_items exists."""
    # Re-create cart_items if the old migrations dropped it.
    if not has_table('cart_items'):
        op.create_table('cart_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('customer_id', 'product_id', name='uq_cart_customer_product')
        )
        op.create_index(op.f('ix_cart_items_customer_id'), 'cart_items', ['customer_id'], unique=False)
        op.create_index(op.f('ix_cart_items_id'), 'cart_items', ['id'], unique=False)
        op.create_index(op.f('ix_cart_items_product_id'), 'cart_items', ['product_id'], unique=False)

    description_type = column_type('products', 'description')
    if description_type is None or not isinstance(description_type, sa.Text):
        op.alter_column('products', 'description',
                   existing_type=sa.String(),
                   type_=sa.Text(),
                   existing_nullable=True)

    for column in ('retail_price', 'wholesale_price'):
        current = column_type('products', column)
        if current is None or not _is_money_numeric(current):
            op.alter_column('products', column,
                       existing_type=sa.Float(),
                       type_=sa.Numeric(precision=10, scale=2),
                       existing_nullable=False,
                       postgresql_using=f'round({column}::numeric, 2)')

    create_index_if_missing(op.f('ix_products_id'), 'products', ['id'])
    create_index_if_missing(op.f('ix_products_name'), 'products', ['name'])


def downgrade() -> None:
    """Revert the products column types. cart_items is left in place."""
    op.drop_index(op.f('ix_products_name'), table_name='products')
    op.drop_index(op.f('ix_products_id'), table_name='products')
    for column in ('wholesale_price', 'retail_price'):
        op.alter_column('products', column,
                   existing_type=sa.Numeric(precision=10, scale=2),
                   type_=sa.Float(),
                   existing_nullable=False)
    op.alter_column('products', 'description',
               existing_type=sa.Text(),
               type_=sa.String(),
               existing_nullable=True)