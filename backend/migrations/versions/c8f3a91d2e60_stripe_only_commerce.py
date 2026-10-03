"""Remove the unused catalog mapping and correlate Stripe refunds.

Revision ID: c8f3a91d2e60
Revises: b7c2d8e4f901
"""
from alembic import op
import sqlalchemy as sa

revision = "c8f3a91d2e60"
down_revision = "b7c2d8e4f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical purchases and entitlements remain valid across the provider change.
    op.drop_column("products", "paddle_product_id")
    op.add_column("purchases", sa.Column("provider_payment_id", sa.String(), nullable=True))
    op.create_index("ix_purchases_provider_payment_id", "purchases", ["provider_payment_id"])


def downgrade() -> None:
    op.drop_index("ix_purchases_provider_payment_id", table_name="purchases")
    op.drop_column("purchases", "provider_payment_id")
    op.add_column("products", sa.Column("paddle_product_id", sa.String(), nullable=True))
    op.create_unique_constraint("uq_products_paddle_product_id", "products", ["paddle_product_id"])
