"""schema base: extension, app role, schema grants

Revision ID: schema_base
Revises:
Create Date: 2026-08-19 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic
revision: str = "schema_base"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("schema",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")

    # keytree_app (the privilege bundle) is created manually per instance, see README:
    # the owner account this migration runs as isn't granted CREATEROLE.
    op.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO keytree_app")

    op.execute("GRANT SELECT ON alembic_version TO keytree_app")  # /health/ready reads it


def downgrade() -> None:
    op.execute("REVOKE USAGE ON SCHEMA public FROM keytree_app")
    op.execute("GRANT ALL ON SCHEMA public TO PUBLIC")
    op.execute("DROP EXTENSION IF EXISTS ltree")
    # we don't drop keytree_app as it would fail if login users are granted it
