"""Seeding for tables the API is not granted write access to."""

from collections.abc import Mapping, Sequence
from typing import Any

from alembic import op
from sqlalchemy import MetaData, Table
from sqlalchemy.dialects.postgresql import insert


def seed(table: str, rows: Sequence[Mapping[str, Any]], key: list[str]) -> None:
    """
    Insert or update existing rows into <table>, matching existing rows on <key>. rows are
    typically TypedDict literals declared in the calling revision.
    """
    if not rows:
        return
    bind = op.get_bind()
    stmt = insert(Table(table, MetaData(), autoload_with=bind)).values(list(rows))
    updates = {c: stmt.excluded[c] for c in rows[0] if c not in key}
    bind.execute(stmt.on_conflict_do_update(index_elements=key, set_=updates))
