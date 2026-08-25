"""base

Revision ID: data_base
Revises:
Create Date: 2026-08-23 13:18:15.276945

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic
revision: str = "data_base"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("data",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
