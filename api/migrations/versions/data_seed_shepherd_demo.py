"""seed shepherd_demo fixture keys (v1 invalid, v2 valid)

Revision ID: data_seed_shepherd_demo
Revises: data_seed_v1_keys
Create Date: 2026-09-27 22:53:02.274951

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from migrations.seed import insert_changeset, insert_key, insert_mode, load_fixture

# revision identifiers, used by Alembic
revision: str = "data_seed_shepherd_demo"
down_revision: str | Sequence[str] | None = "data_seed_v1_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"


def upgrade() -> None:
    bind = op.get_bind()

    fx = load_fixture("shepherd")
    changeset_id = insert_changeset(bind, "keytree_app", ["keytree_superuser"])

    yaml_namespaces = bind.execute(
        text("""
            SELECT n.id, n.name, s.name AS subsystem
            FROM namespace n JOIN subsystem s ON s.id = n.subsystem_id
            WHERE n.format = 'yaml'
        """)
    ).all()

    for namespace_id, namespace_name, subsystem_name in yaml_namespaces:
        mode_id = insert_mode(
            bind,
            namespace_id,
            "shepherd_demo",
            "Mode for testing validation against ShepHerd JSON schemas",
            "keytree_app",
        )

        for version, payload, comment, validation_status in (
            (
                1,
                fx["invalid"],
                "Mode for testing validation against ShepHerd JSON schemas",
                "failed",
            ),
            (2, fx["valid"], "Add valid ShepHerd configuration", "passed"),
        ):
            label = f"{subsystem_name}/{namespace_name}/shepherd_demo/v{version}"
            insert_key(
                bind,
                changeset_id=changeset_id,
                mode_id=mode_id,
                namespace_id=namespace_id,
                version=version,
                label=label,
                created_by="keytree_app",
                comment=comment,
                payload=payload,
                validation_status=validation_status,
            )


def downgrade() -> None:
    pass
