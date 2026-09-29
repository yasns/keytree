"""Shared seeding/insert logic for data-seed migrations."""

import datetime
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from alembic import op
from sqlalchemy import MetaData, Table, column, select, table, text
from sqlalchemy.dialects.postgresql import insert

FIXTURES_DIR = Path(__file__).parent / "fixtures"
_ISO_DATETIME = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\Z")

DEFAULT_MODE_DESCRIPTION = (
    "Placeholder mode, auto-created for namespaces with no other configuration yet"
)

NAMESPACE_T = table("namespace", column("id"), column("name"), column("subsystem_id"))
SUBSYSTEM_T = table("subsystem", column("id"), column("name"))


def upsert(table: str, rows: Sequence[Mapping[str, Any]], key: list[str]) -> None:
    """Insert `rows` into `table`, updating on conflict with `key` -- for tables the API can't write
    to."""
    if not rows:
        return
    bind = op.get_bind()
    stmt = insert(Table(table, MetaData(), autoload_with=bind)).values(list(rows))
    updates = {c: stmt.excluded[c] for c in rows[0] if c not in key}

    if not updates:
        bind.execute(stmt.on_conflict_do_nothing(index_elements=key))
        return
    bind.execute(stmt.on_conflict_do_update(index_elements=key, set_=updates))


def _parse_dates(value):
    if isinstance(value, str):
        return datetime.datetime.fromisoformat(value) if _ISO_DATETIME.match(value) else value
    if isinstance(value, list):
        return [_parse_dates(v) for v in value]
    if isinstance(value, dict):
        return {k: _parse_dates(v) for k, v in value.items()}
    return value


def load_fixture(name: str):
    """Load a fixture, parsing any ISO-8601 datetime strings back to datetime."""
    return _parse_dates(json.loads((FIXTURES_DIR / f"{name}.json").read_text()))


def subsystem_ids(bind) -> dict[str, int]:
    rows = bind.execute(select(SUBSYSTEM_T.c.name, SUBSYSTEM_T.c.id))
    return {name: subsystem_id for name, subsystem_id in rows}


def namespace_ids_global(bind) -> dict[tuple[str, str], int]:
    """Namespace ids across all subsystems, for migrations whose keys span more than one."""
    rows = bind.execute(
        select(SUBSYSTEM_T.c.name, NAMESPACE_T.c.name, NAMESPACE_T.c.id).where(
            NAMESPACE_T.c.subsystem_id == SUBSYSTEM_T.c.id
        )
    )
    return {(sub_name, ns_name): ns_id for sub_name, ns_name, ns_id in rows}


def insert_mode(
    bind, namespace_id: int, name: str, description: str, created_by: str, created_at=None
) -> int:
    return bind.scalar(
        text("""
            INSERT INTO mode (namespace_id, name, description, created_by, created_at)
            VALUES (:namespace_id, :name, :description, :created_by, COALESCE(:created_at, now()))
            RETURNING id
        """),
        {
            "namespace_id": namespace_id,
            "name": name,
            "description": description,
            "created_by": created_by,
            "created_at": created_at,
        },
    )


def insert_changeset(bind, created_by: str, roles: list[str]) -> int:
    return bind.scalar(
        text("""
            INSERT INTO changeset (created_by, committed_with_roles, committed_at)
            VALUES (:created_by, (:roles)::jsonb, now())
            RETURNING id
        """),
        {"created_by": created_by, "roles": json.dumps(roles)},
    )


def insert_key(
    bind,
    *,
    changeset_id: int,
    mode_id: int,
    namespace_id: int,
    version: int,
    label: str,
    created_by: str,
    comment: str,
    payload: str | None = None,
    children: dict[str, int] | None = None,
    created_at=None,
    validation_status: str = "skipped",
) -> int:
    """Insert one staged_edit + key row. Exactly one of `payload`/`children` should be set."""
    staged_edit_id = bind.scalar(
        text("""
            INSERT INTO staged_edit
                (changeset_id, mode_id, expected_version, proposed_payload, proposed_children,
                 comment, validation_status)
            VALUES (:changeset_id, :mode_id, :version, :payload, (:children)::jsonb, :comment,
                    :validation_status)
            RETURNING id
        """),
        {
            "changeset_id": changeset_id,
            "mode_id": mode_id,
            "version": version,
            "payload": payload,
            "children": json.dumps(children) if children is not None else None,
            "comment": comment,
            "validation_status": validation_status,
        },
    )
    return bind.scalar(
        text("""
            INSERT INTO key
                (mode_id, namespace_id, version, label, payload, staged_edit_id, created_by,
                 created_at, comment, validation_status)
            VALUES (:mode_id, :namespace_id, :version, :label, :payload, :staged_edit_id,
                    :created_by, COALESCE(:created_at, now()), :comment, :validation_status)
            RETURNING id
        """),
        {
            "mode_id": mode_id,
            "namespace_id": namespace_id,
            "version": version,
            "label": label,
            "payload": payload,
            "staged_edit_id": staged_edit_id,
            "created_by": created_by,
            "created_at": created_at,
            "comment": comment,
            "validation_status": validation_status,
        },
    )


def insert_key_child(
    bind,
    *,
    parent_key_id: int,
    alias: str,
    child_key_id: int,
    parent_namespace_id: int,
    child_namespace_id: int,
) -> None:
    bind.execute(
        text("""
            INSERT INTO key_child
                (parent_key_id, alias, child_key_id, parent_namespace_id, child_namespace_id)
            VALUES
                (:parent_key_id, :alias, :child_key_id, :parent_namespace_id, :child_namespace_id)
        """),
        {
            "parent_key_id": parent_key_id,
            "alias": alias,
            "child_key_id": child_key_id,
            "parent_namespace_id": parent_namespace_id,
            "child_namespace_id": child_namespace_id,
        },
    )


def insert_bundle_key(
    bind,
    *,
    changeset_id: int,
    mode_id: int,
    namespace_id: int,
    version: int,
    label: str,
    created_by: str,
    comment: str,
    children: dict[str, tuple[int, int]],
    created_at=None,
    validation_status: str = "skipped",
) -> int:
    """insert_key with `children` (alias -> (key_id, namespace_id)), then wire key_child rows."""
    key_id = insert_key(
        bind,
        changeset_id=changeset_id,
        mode_id=mode_id,
        namespace_id=namespace_id,
        version=version,
        label=label,
        created_by=created_by,
        created_at=created_at,
        comment=comment,
        children={alias: child_key_id for alias, (child_key_id, _) in children.items()},
        validation_status=validation_status,
    )
    for alias, (child_key_id, child_namespace_id) in children.items():
        insert_key_child(
            bind,
            parent_key_id=key_id,
            alias=alias,
            child_key_id=child_key_id,
            parent_namespace_id=namespace_id,
            child_namespace_id=child_namespace_id,
        )
    return key_id
