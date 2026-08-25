"""grant privileges

Revision ID: schema_grants
Revises: schema_base
Create Date: 2026-08-24 17:12:55.226759

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic
revision: str = "schema_grants"
down_revision: str | Sequence[str] | None = "schema_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # keytree_app (the privilege bundle) is created manually per instance, see README
    op.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO keytree_app")

    op.execute("GRANT SELECT ON alembic_version TO keytree_app")  # /health/ready reads it


def downgrade() -> None:
    op.execute("REVOKE USAGE ON SCHEMA public FROM keytree_app")
    op.execute("GRANT ALL ON SCHEMA public TO PUBLIC")
    # we don't drop keytree_app as it would fail if login users are granted it
