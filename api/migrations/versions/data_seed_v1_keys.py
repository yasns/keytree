"""seed an empty v1 key for every namespace's default mode

Revision ID: data_seed_v1_keys
Revises: data_seed_default_modes
Create Date: 2026-08-31 16:57:10.44725

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic
revision: str = "data_seed_v1_keys"
down_revision: str | Sequence[str] | None = "data_seed_default_modes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"


def upgrade() -> None:
    bind = op.get_bind()

    # raw SQL: no commit path exists yet, and seed() is reserved for tables the API can't write
    if bind.scalar(text("SELECT 1 FROM key LIMIT 1")) is not None:
        return

    changeset_id = bind.scalar(
        text("""
            INSERT INTO changeset (created_by, committed_with_roles, committed_at)
            VALUES ('keytree_app', '["keytree_superuser"]'::jsonb, now())
            RETURNING id
        """)
    )

    # bundle namespace's proposed_children is a placeholder, backfilled below once child keys exist
    _ = bind.execute(
        text("""
            INSERT INTO staged_edit
                (changeset_id, mode_id, expected_version, proposed_payload, proposed_children,
                 comment, validation_status)
            SELECT :changeset_id, m.id, 1,
                   CASE WHEN n.category IS NULL THEN NULL ELSE '' END,
                   CASE WHEN n.category IS NULL THEN '{}'::jsonb ELSE NULL END,
                   'Bootstrap v1 seed', 'skipped'
            FROM mode m JOIN namespace n ON n.id = m.namespace_id
            WHERE m.name = 'default'
        """),
        {"changeset_id": changeset_id},
    )

    _ = bind.execute(
        text("""
            INSERT INTO key
                (mode_id, namespace_id, version, label, payload, staged_edit_id, created_by,
                comment, validation_status)
            SELECT m.id, n.id, 1,
                   s.name || '/' || n.name || '/' || m.name || '/v1',
                   CASE WHEN n.category IS NULL THEN NULL ELSE '' END,
                   se.id, 'keytree_app', 'Bootstrap v1 seed', se.validation_status
            FROM staged_edit se
            JOIN mode m ON m.id = se.mode_id
            JOIN namespace n ON n.id = m.namespace_id
            JOIN subsystem s ON s.id = n.subsystem_id
            WHERE se.changeset_id = :changeset_id
        """),
        {"changeset_id": changeset_id},
    )

    # (namespace_id, version=1) is unambiguous: one default mode, one version, per namespace
    _ = bind.execute(
        text("""
            INSERT INTO key_child
                (parent_key_id, alias, child_key_id, parent_namespace_id, child_namespace_id)
            SELECT pk.id, ne.alias, ck.id, ne.parent_namespace_id, ne.child_namespace_id
            FROM namespace_edge ne
            JOIN key pk ON pk.namespace_id = ne.parent_namespace_id AND pk.version = 1
            JOIN key ck ON ck.namespace_id = ne.child_namespace_id AND ck.version = 1
        """)
    )

    # backfill proposed_children now that the child keys it references exist
    _ = bind.execute(
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
