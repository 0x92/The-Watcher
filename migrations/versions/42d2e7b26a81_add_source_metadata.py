"""add source metadata columns

Revision ID: 42d2e7b26a81
Revises: 8f0c6e3c4a99
Create Date: 2025-09-23 18:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "42d2e7b26a81"
down_revision: Union[str, Sequence[str], None] = "8f0c6e3c4a99"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "sources"


def upgrade() -> None:
    op.add_column(
        TABLE_NAME,
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(TABLE_NAME, sa.Column("tags_json", sa.JSON(), nullable=True))
    op.add_column(TABLE_NAME, sa.Column("notes", sa.Text(), nullable=True))
    op.execute(f"UPDATE {TABLE_NAME} SET priority = 0 WHERE priority IS NULL")
    op.alter_column(TABLE_NAME, "priority", server_default=None)


def downgrade() -> None:
    op.drop_column(TABLE_NAME, "notes")
    op.drop_column(TABLE_NAME, "tags_json")
    op.drop_column(TABLE_NAME, "priority")
