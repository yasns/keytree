"""base

Revision ID: tree_base
Revises:
Create Date: 2026-08-19 12:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic
revision: str = "tree_base"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("tree",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
