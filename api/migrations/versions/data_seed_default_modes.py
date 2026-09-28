"""seed one starter mode per namespace

Revision ID: data_seed_default_modes
Revises: data_seed_demo_roles
Create Date: 2026-08-26 11:26:56.807619

"""

from collections.abc import Sequence

from alembic import op

from migrations.seed import DEFAULT_MODE_DESCRIPTION, namespace_ids_global, upsert

# revision identifiers, used by Alembic
revision: str = "data_seed_default_modes"
down_revision: str | Sequence[str] | None = "data_seed_demo_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"


def upgrade() -> None:
    bind = op.get_bind()

    # we need a user to attribute the modes to
    upsert(
        "app_user",
        [{"cern_login": "keytree_app", "display_name": "System"}],
        key=["cern_login"],
    )

    upsert(
        "mode",
        [
            {
                "namespace_id": namespace_id,
                "name": "default",
                "description": DEFAULT_MODE_DESCRIPTION,
                "created_by": "keytree_app",
            }
            for namespace_id in namespace_ids_global(bind).values()
        ],
        key=["namespace_id", "name"],
    )


def downgrade() -> None:
    pass
