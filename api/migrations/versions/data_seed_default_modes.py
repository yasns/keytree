"""seed one starter mode per namespace

Revision ID: data_seed_default_modes
Revises: data_seed_legacy_roles
Create Date: 2026-08-26 11:26:56.807619

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import column, select, table

from migrations.seed import seed

# revision identifiers, used by Alembic
revision: str = "data_seed_default_modes"
down_revision: str | Sequence[str] | None = "data_seed_legacy_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"


def upgrade() -> None:
    # we need a user to attribute the modes to
    seed(
        "app_user",
        [{"cern_login": "keytree_app", "display_name": "System"}],
        key=["cern_login"],
    )

    namespace = table("namespace", column("id"))
    namespace_ids = op.get_bind().scalars(select(namespace.c.id)).all()

    seed(
        "mode",
        [
            {
                "namespace_id": namespace_id,
                "name": "default",
                "description": "Bootstrap default mode",
                "created_by": "keytree_app",
            }
            for namespace_id in namespace_ids
        ],
        key=["namespace_id", "name"],
    )


def downgrade() -> None:
    pass
