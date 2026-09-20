"""add paraphrase_orders

Revision ID: b7c2d8e4f901
Revises: a1b2c3d4e5f6
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c2d8e4f901'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema -- anonymous paraphrase PWYW purchases (see
    models.ParaphraseOrder). Idempotency comes from the two unique keys:
    one hint per browser (hint), one row per Paddle transaction
    (provider_order_id), so duplicate webhook deliveries can never fan
    out into multiple unlocks."""
    op.create_table(
        'paraphrase_orders',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('hint', sa.String(), nullable=False),
        sa.Column('provider_order_id', sa.String(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('hint', name='uq_paraphrase_orders_hint'),
        sa.UniqueConstraint('provider_order_id', name='uq_paraphrase_orders_provider_order'),
    )
    op.create_index('ix_paraphrase_orders_hint', 'paraphrase_orders', ['hint'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_paraphrase_orders_hint', table_name='paraphrase_orders')
    op.drop_table('paraphrase_orders')