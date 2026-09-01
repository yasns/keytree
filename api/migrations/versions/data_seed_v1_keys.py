"""seed an empty v1 key for every node's default mode

Revision ID: data_seed_v1_keys
Revises: data_default_modes
Create Date: 2026-08-31 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic
revision: str = "data_seed_v1_keys"
down_revision: str | Sequence[str] | None = "data_default_modes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"


def upgrade() -> None:
    bind = op.get_bind()

    # Bootstraps a commit path that doesn't exist yet, so this seeds tables the API is
    # granted write access to (key, key_child, staged_edit, changeset) directly with plain
    # SQL rather than migrations.seed.seed(), whose docstring reserves it for tables the
    # API cannot write.
    if bind.scalar(text("SELECT 1 FROM key LIMIT 1")) is not None:
        return

    changeset_id = bind.scalar(
        text("""
            INSERT INTO changeset (created_by, comment, committed_with_roles, committed_at)
            VALUES ('keytree_app', 'Bootstrap v1 seed', '["keytree_superuser"]'::jsonb, now())
            RETURNING id
        """)
    )

    # One staged edit per (node, default mode). A bundle node gets a placeholder
    # `proposed_children`, corrected below once the child keys it should reference exist.
    bind.execute(
        text("""
            INSERT INTO staged_edit
                (changeset_id, mode_id, proposed_payload, proposed_children, comment,
                 validation_status)
            SELECT :changeset_id, m.id,
                   CASE WHEN n.category IS NULL THEN NULL ELSE '' END,
                   CASE WHEN n.category IS NULL THEN '{}'::jsonb ELSE NULL END,
                   'Bootstrap v1 seed', 'skipped'
            FROM mode m JOIN node n ON n.id = m.node_id
            WHERE m.name = 'default'
        """),
        {"changeset_id": changeset_id},
    )

    bind.execute(
        text("""
            INSERT INTO key
                (mode_id, node_id, version, label, payload, staged_edit_id, created_by, comment)
            SELECT m.id, n.id, 1,
                   s.name || '/' || n.name || '/' || m.name || '/v1',
                   CASE WHEN n.category IS NULL THEN NULL ELSE '' END,
                   se.id, 'keytree_app', 'Bootstrap v1 seed'
            FROM staged_edit se
            JOIN mode m ON m.id = se.mode_id
            JOIN node n ON n.id = m.node_id
            JOIN subsystem s ON s.id = n.subsystem_id
            WHERE se.changeset_id = :changeset_id
        """),
        {"changeset_id": changeset_id},
    )

    # Pin every node_edge to the two nodes' v1 keys. A node has exactly one v1 key (one
    # default mode, one version), so (node_id, version=1) resolves it unambiguously.
    bind.execute(
        text("""
            INSERT INTO key_child
                (parent_key_id, alias, child_key_id, parent_node_id, child_node_id)
            SELECT pk.id, ne.alias, ck.id, ne.parent_node_id, ne.child_node_id
            FROM node_edge ne
            JOIN key pk ON pk.node_id = ne.parent_node_id AND pk.version = 1
            JOIN key ck ON ck.node_id = ne.child_node_id AND ck.version = 1
        """)
    )

    # Backfill the bundle staged_edits' proposed_children now that the child keys exist,
    # so each staged edit matches the key it produced.
    bind.execute(
        text("""
            UPDATE staged_edit se SET proposed_children = agg.children
            FROM (
                SELECT parent_key_id, jsonb_object_agg(alias, child_key_id) AS children
                FROM key_child
                GROUP BY parent_key_id
            ) agg
            JOIN key k ON k.id = agg.parent_key_id
            WHERE se.id = k.staged_edit_id
        """)
    )


def downgrade() -> None:
    pass
