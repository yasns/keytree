import re
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.errors import InvalidRegularExpression, QueryCanceled
from pydantic import BaseModel
from sqlalchemy import func, select, text, tuple_
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import aliased
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import AppUser, Key, KeyChild, Mode, Node, NodeEdge, StagedEdit, Subsystem

router = APIRouter(
    prefix="/keys",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["keys"],
)


class KeyRefOut(BaseModel):
    mode_name: str
    version: int
    label: str


class KeyOut(BaseModel):
    id: int
    label: str
    version: int
    payload: str | None
    """None for bundles."""
    created_by: str
    created_by_display_name: str
    created_at: datetime
    comment: str
    based_on: KeyRefOut | None
    """The key this was forked/copied from, or its previous version otherwise."""

    model_config = {"from_attributes": True}


class KeyChildMetaOut(BaseModel):
    id: int | None
    alias: str
    label: str | None
    node_id: int
    node_name: str
    subsystem_name: str
    category: str | None
    """None for bundles."""
    payload: str | None
    """Only populated for external children."""
    mode_name: str | None
    version: int | None
    created_by: str | None
    created_at: datetime | None
    comment: str | None


_KeyLocator = tuple[str, str, str, int]
"""(subsystem_name, node_name, mode_name, version)."""


async def keys_by_locator(
    locators: list[_KeyLocator], session: SessionDep
) -> dict[_KeyLocator, Key]:
    """Missing locators are simply absent from the result."""
    if not locators:
        return {}
    rows = await session.execute(
        select(Subsystem.name, Node.name, Mode.name, Key)
        .select_from(Key)
        .join(Mode, Mode.id == Key.mode_id)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .where(tuple_(Subsystem.name, Node.name, Mode.name, Key.version).in_(locators))
    )
    return {(s, n, m, key.version): key for s, n, m, key in rows.tuples()}


async def keys_or_404(locators: list[_KeyLocator], session: SessionDep) -> list[Key]:
    """In request order."""
    found = await keys_by_locator(locators, session)
    keys: list[Key] = []
    for locator in locators:
        key = found.get(locator)
        if key is None:
            raise HTTPException(status_code=404, detail="key not found")
        keys.append(key)
    return keys


async def key_or_404(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> Key:
    [key] = await keys_or_404([(subsystem_name, node_name, mode_name, version)], session)
    return key


def _build_key_detail(
    key: Key,
    display_name: str,
    ancestor_mode_name: str | None,
    ancestor_version: int | None,
    ancestor_label: str | None,
) -> KeyOut:
    return KeyOut(
        id=key.id,
        label=key.label,
        version=key.version,
        payload=key.payload,
        created_by=key.created_by,
        created_by_display_name=display_name,
        created_at=key.created_at,
        comment=key.comment,
        based_on=(
            KeyRefOut(mode_name=ancestor_mode_name, version=ancestor_version, label=ancestor_label)
            if ancestor_mode_name is not None
            else None
        ),
    )


class KeyMatchOut(BaseModel):
    label: str
    subsystem_name: str
    node_name: str
    mode_name: str
    version: int


_VERSION_SEGMENT = re.compile(r"/v\d+$")


@router.get("/search")
async def search_keys(
    session: SessionDep,
    q: Annotated[str, Query(min_length=1)],
    field: Literal["label", "payload"] = "label",
    regex: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[KeyMatchOut]:
    """Keys whose label or payload matches `q`, restricted to each mode's tip version unless the
    query already names one."""
    column = Key.label if field == "label" else Key.payload
    names_version = field == "label" and bool(_VERSION_SEGMENT.search(q))

    if regex:
        match = column.op("~*")(q)
    elif names_version:
        # Anchor to end: a plain substring match would also hit v10 when q ends in v1.
        match = column.op("~*")(f"{re.escape(q)}$")
    else:
        match = column.icontains(q, autoescape=True)

    filters = [match, Node.retired_at.is_(None), Subsystem.retired_at.is_(None)]

    if field == "payload" or not names_version:
        other = aliased(Key)
        tip_version = (
            select(func.max(other.version)).where(other.mode_id == Key.mode_id).scalar_subquery()
        )
        filters.append(Key.version == tip_version)

    filters.append(Node.category.is_distinct_from("external"))

    stmt = (
        select(Key.label, Subsystem.name, Node.name, Mode.name, Key.version)
        .select_from(Key)
        .join(Mode, Mode.id == Key.mode_id)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .where(*filters)
        .order_by(Key.label)
        .limit(limit)
    )

    if regex:
        # A user-typed regex can be malformed or pathologically slow; neither may wedge the session.
        await session.execute(text("SET LOCAL statement_timeout = '3s'"))
    try:
        rows = await session.execute(stmt)
    except DBAPIError as err:
        if not (regex and isinstance(err.orig, InvalidRegularExpression | QueryCanceled)):
            raise
        await session.rollback()
        return []

    return [
        KeyMatchOut(label=label, subsystem_name=s, node_name=n, mode_name=m, version=v)
        for label, s, n, m, v in rows.tuples()
    ]


@router.get("/{subsystem_name}/{node_name}/{mode_name}/{version}")
async def get_key(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> KeyOut:
    """Fetches a single key by (subsystem, node, mode, version)."""
    key = await key_or_404(subsystem_name, node_name, mode_name, version, session)

    ancestor = aliased(Key)
    ancestor_mode = aliased(Mode)
    row = (
        await session.execute(
            select(AppUser.display_name, ancestor_mode.name, ancestor.version, ancestor.label)
            .select_from(StagedEdit)
            .outerjoin(
                ancestor,
                ancestor.id == func.coalesce(StagedEdit.copied_from_key_id, StagedEdit.base_key_id),
            )
            .outerjoin(ancestor_mode, ancestor_mode.id == ancestor.mode_id)
            .outerjoin(AppUser, AppUser.cern_login == key.created_by)
            .where(StagedEdit.id == key.staged_edit_id)
        )
    ).first()
    assert row is not None
    display_name, ancestor_mode_name, ancestor_version, ancestor_label = row
    assert display_name is not None
    return _build_key_detail(
        key, display_name, ancestor_mode_name, ancestor_version, ancestor_label
    )


_ChildRow = tuple[str, Key | None, int, str, str, str | None, str | None]


def _build_child_meta(row: _ChildRow) -> KeyChildMetaOut:
    """Unset child stays as a row with a null key, not skipped."""
    alias, key, node_id, node_name, subsystem_name, category, mode_name = row
    return KeyChildMetaOut(
        id=key.id if key else None,
        alias=alias,
        label=key.label if key else None,
        node_id=node_id,
        node_name=node_name,
        subsystem_name=subsystem_name,
        category=category,
        payload=key.payload if key and category == "external" else None,
        mode_name=mode_name,
        version=key.version if key else None,
        created_by=key.created_by if key else None,
        created_at=key.created_at if key else None,
        comment=key.comment if key else None,
    )


@router.get("/{subsystem_name}/{node_name}/{mode_name}/{version}/children")
async def get_key_children(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> list[KeyChildMetaOut]:
    """One level of a bundle: one row per alias, whether emptied or not, crossing subsystem
    boundaries freely."""
    parent = await key_or_404(subsystem_name, node_name, mode_name, version, session)

    child = aliased(Key)

    rows = await session.execute(
        select(
            NodeEdge.alias,
            child,
            Node.id,
            Node.name,
            Subsystem.name,
            Node.category,
            Mode.name,
        )
        .select_from(NodeEdge)
        .join(Node, Node.id == NodeEdge.child_node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .outerjoin(
            KeyChild,
            (KeyChild.parent_key_id == parent.id) & (KeyChild.alias == NodeEdge.alias),
        )
        .outerjoin(child, child.id == KeyChild.child_key_id)
        .outerjoin(Mode, Mode.id == child.mode_id)
        .where(NodeEdge.parent_node_id == parent.node_id)
        .order_by(NodeEdge.alias)
    )

    return [_build_child_meta(cast("_ChildRow", row)) for row in rows.tuples()]
