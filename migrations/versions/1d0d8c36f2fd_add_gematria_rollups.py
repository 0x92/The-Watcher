"""add gematria rollups table

Revision ID: 1d0d8c36f2fd
Revises: 42d2e7b26a81
Create Date: 2025-09-24 15:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1d0d8c36f2fd"
down_revision: Union[str, Sequence[str], None] = "42d2e7b26a81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "gematria_rollups"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("window_hours", sa.Integer(), nullable=False),
        sa.Column("scheme", sa.String(length=50), nullable=False),
        sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "scope",
            "window_hours",
            "scheme",
            name="uq_gematria_rollups_scope_window_scheme",
        ),
    )
    op.create_index("ix_gematria_rollups_scope", TABLE_NAME, ["scope"])
    op.create_index(
        "ix_gematria_rollups_window_scheme",
        TABLE_NAME,
        ["window_hours", "scheme"],
    )
    op.alter_column(TABLE_NAME, "computed_at", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_gematria_rollups_window_scheme", table_name=TABLE_NAME)
    op.drop_index("ix_gematria_rollups_scope", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
