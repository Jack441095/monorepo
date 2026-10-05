"""Index the unsent-confirmation sweep.

Revision ID: f9c2d4e6a8b1
Revises: e7a1b2c3d4f5
"""
from alembic import op
import sqlalchemy as sa

revision = "f9c2d4e6a8b1"
down_revision = "e7a1b2c3d4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The admin unsent-confirmations sweep filters on
    # confirmation_email_sent_at IS NULL. Sent rows dominate the table over
    # time, so a partial index keeps that sweep cheap without indexing every
    # fulfilled purchase.
    op.create_index(
        "ix_purchases_unsent_confirmation",
        "purchases",
        ["purchased_at"],
        postgresql_where=sa.text("confirmation_email_sent_at IS NULL"),
    )


def downgrade() -> None:
    # Guard: drain GET /admin/purchases/unsent-confirmations to zero before
    # downgrading. Dropping this index while unsent rows exist does not lose
    # data, but it blinds the sweep that finds them -- and downgrading past
    # e7a1b2c3d4f5 drops confirmation_email_sent_at itself, which destroys the
    # only record of which licences still owe a confirmation email.
    op.drop_index("ix_purchases_unsent_confirmation", table_name="purchases")
