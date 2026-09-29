"""seed shepherd_demo fixture keys (v1 invalid, v2 valid) and bundles of them up the tree

Revision ID: data_seed_shepherd_demo
Revises: data_seed_v1_keys
Create Date: 2026-09-27 22:53:02.274951

"""

from collections import defaultdict
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from migrations.seed import (
    insert_bundle_key,
    insert_changeset,
    insert_key,
    insert_mode,
    load_fixture,
    namespace_ids_global,
)

# revision identifiers, used by Alembic
revision: str = "data_seed_shepherd_demo"
down_revision: str | Sequence[str] | None = "data_seed_v1_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"

MODE_NAME = "shepherd_demo"
VERSIONS = ((1, "failed"), (2, "passed"))


def _parents_children_first(edges: list[tuple[int, int, str]]) -> list[int]:
    """Namespaces that have children, ordered so every child precedes its parents."""
    kids: dict[int, list[int]] = defaultdict(list)
    for parent, child, _ in edges:
        kids[parent].append(child)

    order: list[int] = []
    seen: set[int] = set()

    def visit(namespace_id: int) -> None:
        if namespace_id in seen:
            return
        seen.add(namespace_id)
        for child in kids.get(namespace_id, ()):
            visit(child)
        if namespace_id in kids:
            order.append(namespace_id)

    for parent in list(kids):
        visit(parent)
    return order


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

    keys: dict[tuple[int, int], int] = {}
    for namespace_id, namespace_name, subsystem_name in yaml_namespaces:
        mode_id = insert_mode(
            bind,
            namespace_id,
            MODE_NAME,
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
            label = f"{subsystem_name}/{namespace_name}/{MODE_NAME}/v{version}"
            keys[(namespace_id, version)] = insert_key(
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

    edges = [
        tuple(row)
        for row in bind.execute(
            text("SELECT parent_namespace_id, child_namespace_id, alias FROM namespace_edge")
        )
    ]
    names = {ns_id: key for key, ns_id in namespace_ids_global(bind).items()}
    comment = "Bundle of ShepHerd fixture children"

    for parent_id in _parents_children_first(edges):
        # children without a shepherd key (non-yaml namespaces) are left out of the bundle
        bundles = {
            version: {
                alias: (keys[(child_id, version)], child_id)
                for parent, child_id, alias in edges
                if parent == parent_id and (child_id, version) in keys
            }
            for version, _ in VERSIONS
        }
        if not any(bundles.values()):
            continue

        subsystem_name, namespace_name = names[parent_id]
        mode_id = insert_mode(bind, parent_id, MODE_NAME, comment, "keytree_app")
        for version, validation_status in VERSIONS:
            keys[(parent_id, version)] = insert_bundle_key(
                bind,
                changeset_id=changeset_id,
                mode_id=mode_id,
                namespace_id=parent_id,
                version=version,
                label=f"{subsystem_name}/{namespace_name}/{MODE_NAME}/v{version}",
                created_by="keytree_app",
                comment=comment,
                children=bundles[version],
                validation_status=validation_status,
            )


def downgrade() -> None:
    pass
