"""Fix gematria primary key to include scheme column.

Revision ID: 8f0c6e3c4a99
Revises: f34c0dfecc5c
Create Date: 2025-09-23 10:30:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "8f0c6e3c4a99"
down_revision: Union[str, Sequence[str], None] = "f34c0dfecc5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("gematria_pkey", "gematria", type_="primary")
    op.create_primary_key("gematria_pkey", "gematria", ["item_id", "scheme"])


def downgrade() -> None:
    op.drop_constraint("gematria_pkey", "gematria", type_="primary")
    op.create_primary_key("gematria_pkey", "gematria", ["item_id"])
