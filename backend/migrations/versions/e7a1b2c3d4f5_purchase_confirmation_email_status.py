"""Record purchase confirmation email delivery.

Revision ID: e7a1b2c3d4f5
Revises: c8f3a91d2e60
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a1b2c3d4f5"
down_revision = "c8f3a91d2e60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchases",
        sa.Column("confirmation_email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Rows committed before this column existed sent their confirmation inside
    # the old fulfilment transaction, so a committed row implies a sent email.
    # Backfill from purchased_at; only rows created after this migration stay
    # NULL (pending) until the post-commit send marks them.
    op.execute(
        "UPDATE purchases SET confirmation_email_sent_at = purchased_at "
        "WHERE confirmation_email_sent_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("purchases", "confirmation_email_sent_at")
