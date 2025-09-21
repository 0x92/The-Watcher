"""add patterns table

Revision ID: f34c0dfecc5c
Revises: 6fcfdba8f775
Create Date: 2025-09-22 00:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f34c0dfecc5c"
down_revision: Union[str, Sequence[str], None] = "6fcfdba8f775"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("top_terms", sa.JSON(), nullable=True),
        sa.Column("anomaly_score", sa.Float(), nullable=True),
        sa.Column("item_ids", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patterns_created_at", "patterns", ["created_at"])
    op.create_index("ix_patterns_anomaly_score", "patterns", ["anomaly_score"])


def downgrade() -> None:
    op.drop_index("ix_patterns_anomaly_score", table_name="patterns")
    op.drop_index("ix_patterns_created_at", table_name="patterns")
    op.drop_table("patterns")
