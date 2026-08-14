"""add product paddle_product_id

Revision ID: 377a0020b4c5
Revises: 90aab51af2f7
Create Date: 2026-08-14 10:22:02.126244

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '377a0020b4c5'
down_revision: Union[str, Sequence[str], None] = '90aab51af2f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable: a Product row can exist before Paddle is wired up at all.
    # Unique so two internal products can never collide on the same real
    # Paddle catalog item.
    op.add_column('products', sa.Column('paddle_product_id', sa.String(), nullable=True))
    op.create_unique_constraint('uq_products_paddle_product_id', 'products', ['paddle_product_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_products_paddle_product_id', 'products', type_='unique')
    op.drop_column('products', 'paddle_product_id')
