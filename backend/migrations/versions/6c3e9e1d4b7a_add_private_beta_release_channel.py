"""allow private-beta release channel

Revision ID: 6c3e9e1d4b7a
Revises: 377a0020b4c5
Create Date: 2026-08-25 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "6c3e9e1d4b7a"
down_revision: Union[str, Sequence[str], None] = "377a0020b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_releases_channel", "releases", type_="check")
    op.create_check_constraint(
        "ck_releases_channel",
        "releases",
        "channel IN ('dev','beta','private-beta','stable')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_releases_channel", "releases", type_="check")
    op.create_check_constraint(
        "ck_releases_channel",
        "releases",
        "channel IN ('dev','beta','stable')",
    )
