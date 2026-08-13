"""add purchase price_id

Revision ID: 90aab51af2f7
Revises: 34e889215e56
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90aab51af2f7'
down_revision: Union[str, Sequence[str], None] = '34e889215e56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable: existing rows (and any purchase recorded before real Paddle
    # price IDs existed) have no price_id to backfill. Tracks which of the
    # intro/regular prices was actually charged, distinct from product_id.
    op.add_column('purchases', sa.Column('price_id', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('purchases', 'price_id')
