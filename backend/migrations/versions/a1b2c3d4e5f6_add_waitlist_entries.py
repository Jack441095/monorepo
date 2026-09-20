"""add waitlist_entries table

Revision ID: a1b2c3d4e5f6
Revises: 6c3e9e1d4b7a
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6c3e9e1d4b7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waitlist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("product_id", sa.String(), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("use_case", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("email", "product_id", name="uq_waitlist_email_product"),
    )


def downgrade() -> None:
    op.drop_table("waitlist_entries")
