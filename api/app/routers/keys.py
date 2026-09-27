import re
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.errors import InvalidRegularExpression, QueryCanceled
from pydantic import BaseModel, BeforeValidator
from sqlalchemy import func, select, text, tuple_
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import aliased
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import (
    AppUser,
    Key,
    KeyChild,
    Mode,
    Namespace,
    NamespaceEdge,
    StagedEdit,
    Subsystem,
)

router = APIRouter(
    prefix="/keys",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["keys"],
)


class KeyRefOut(BaseModel):
    mode_name: str
    version: int
    label: str


class RetiredRefOut(BaseModel):
    label: str
    reason: Literal["decommissioned", "mode_archived"]


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
    validation_status: str
    decommissioned_at: datetime | None
    """None while active."""
    decommissioned_by: str | None
    """None while active."""
    decommissioned_by_display_name: str | None
    """None while active."""
    retired_descendants: list[RetiredRefOut]
    """Descendants (via key_child, any depth) that are decommissioned or whose mode is archived."""
    based_on: KeyRefOut | None
    """The key this was forked/copied from, or its previous version otherwise."""

    model_config = {"from_attributes": True}


class KeyChildMetaOut(BaseModel):
    id: int | None
    alias: str
    label: str | None
    namespace_id: int
    namespace_name: str
    subsystem_name: str
    category: str | None
    """None for bundles."""
    format: str | None
    """None for bundles; also null on external leaves until one gets a real format."""
    payload: str | None
    """Only populated for external children."""
    mode_name: str | None
    version: int | None
    created_by: str | None
    created_at: datetime | None
    comment: str | None


class AggregateOut(BaseModel):
    alias: str | None
    """None on the root."""
    label: str | None
    """None when the alias is an emptied slot."""
    format: str | None
    """None for bundles; otherwise the syntax of payload."""
    payload: str | None
    """None for bundles and emptied slots."""
    children: list["AggregateOut"] = []


KeyVersion = Annotated[int, BeforeValidator(lambda v: v.removeprefix("v"))]
"""Takes `v3` as well as `3`."""


_KeyLocator = tuple[str, str, str, int]
"""(subsystem_name, namespace_name, mode_name, version)."""


async def keys_by_locator(
    locators: list[_KeyLocator], session: SessionDep
) -> dict[_KeyLocator, Key]:
    """Missing locators are simply absent from the result."""
    if not locators:
        return {}
    rows = await session.execute(
        select(Subsystem.name, Namespace.name, Mode.name, Key)
        .select_from(Key)
        .join(Mode, Mode.id == Key.mode_id)
        .join(Namespace, Namespace.id == Mode.namespace_id)
        .join(Subsystem, Subsystem.id == Namespace.subsystem_id)
        .where(tuple_(Subsystem.name, Namespace.name, Mode.name, Key.version).in_(locators))
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


async def key_ancestry(
    key_ids: set[int], session: SessionDep
) -> tuple[dict[int, str | None], dict[int, dict[str, int]]]:
    """Key id -> payload, and key id -> {alias: child_key_id}."""
    if not key_ids:
        return {}, {}
    payload_rows = await session.execute(select(Key.id, Key.payload).where(Key.id.in_(key_ids)))
    payloads = dict(payload_rows.tuples().all())
    child_rows = await session.execute(
        select(KeyChild.parent_key_id, KeyChild.alias, KeyChild.child_key_id).where(
            KeyChild.parent_key_id.in_(key_ids)
        )
    )
    children: dict[int, dict[str, int]] = {}
    for parent_key_id, alias, child_key_id in child_rows.tuples():
        children.setdefault(parent_key_id, {})[alias] = child_key_id
    return payloads, children


async def key_or_404(
    subsystem_name: str, namespace_name: str, mode_name: str, version: int, session: SessionDep
) -> Key:
    [key] = await keys_or_404([(subsystem_name, namespace_name, mode_name, version)], session)
    return key


def _build_key_detail(
    key: Key,
    display_name: str,
    ancestor_mode_name: str | None,
    ancestor_version: int | None,
    ancestor_label: str | None,
    decommissioner_display_name: str | None,
    retired_descendants: list[RetiredRefOut],
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
        validation_status=key.validation_status,
        decommissioned_at=key.decommissioned_at,
        decommissioned_by=key.decommissioned_by,
        decommissioned_by_display_name=decommissioner_display_name,
        retired_descendants=retired_descendants,
        based_on=(
            KeyRefOut(mode_name=ancestor_mode_name, version=ancestor_version, label=ancestor_label)
            if ancestor_mode_name is not None
            else None
        ),
    )


class KeyMatchOut(BaseModel):
    label: str
    subsystem_name: str
    namespace_name: str
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
    """Keys matching `q`, restricted to each mode's tip unless the query already names a version."""
    column = Key.label if field == "label" else Key.payload
    names_version = field == "label" and bool(_VERSION_SEGMENT.search(q))

    if regex:
        match = column.op("~*")(q)
    elif names_version:
        # Anchor to end: a plain substring match would also hit v10 when q ends in v1.
        match = column.op("~*")(f"{re.escape(q)}$")
    else:
        match = column.icontains(q, autoescape=True)

    filters = [match]

    if field == "payload" or not names_version:
        other = aliased(Key)
        tip_version = (
            select(func.max(other.version)).where(other.mode_id == Key.mode_id).scalar_subquery()
        )
        filters.append(Key.version == tip_version)

    filters.append(Namespace.category.is_distinct_from("external"))

    stmt = (
        select(Key.label, Subsystem.name, Namespace.name, Mode.name, Key.version)
        .select_from(Key)
        .join(Mode, Mode.id == Key.mode_id)
        .join(Namespace, Namespace.id == Mode.namespace_id)
        .join(Subsystem, Subsystem.id == Namespace.subsystem_id)
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
        KeyMatchOut(label=label, subsystem_name=s, namespace_name=n, mode_name=m, version=v)
        for label, s, n, m, v in rows.tuples()
    ]


async def _retired_descendants(key_id: int, session: SessionDep) -> list[RetiredRefOut]:
    """Descendants (via key_child, any depth) that are decommissioned or whose mode is archived."""
    descendants = (
        select(KeyChild.child_key_id).where(KeyChild.parent_key_id == key_id).cte(recursive=True)
    )
    child = aliased(KeyChild)
    descendants = descendants.union(
        select(child.child_key_id).join(
            descendants, child.parent_key_id == descendants.c.child_key_id
        )
    )

    rows = await session.execute(
        select(Key.label, Key.decommissioned_at, Mode.archived_at)
        .join(descendants, Key.id == descendants.c.child_key_id)
        .join(Mode, Mode.id == Key.mode_id)
        .where(Key.decommissioned_at.is_not(None) | Mode.archived_at.is_not(None))
    )
    return [
        RetiredRefOut(
            label=label,
            reason="decommissioned" if decommissioned_at is not None else "mode_archived",
        )
        for label, decommissioned_at, _archived_at in rows.tuples()
    ]


@router.get("/{subsystem_name}/{namespace_name}/{mode_name}/{version}")
async def get_key(
    subsystem_name: str,
    namespace_name: str,
    mode_name: str,
    version: KeyVersion,
    session: SessionDep,
) -> KeyOut:
    """Fetches a single key by (subsystem, namespace, mode, version)."""
    key = await key_or_404(subsystem_name, namespace_name, mode_name, version, session)

    ancestor = aliased(Key)
    ancestor_mode = aliased(Mode)
    decommissioner = aliased(AppUser)
    row = (
        await session.execute(
            select(
                AppUser.display_name,
                ancestor_mode.name,
                ancestor.version,
                ancestor.label,
                decommissioner.display_name,
            )
            .select_from(StagedEdit)
            .outerjoin(
                ancestor,
                ancestor.id == func.coalesce(StagedEdit.copied_from_key_id, StagedEdit.base_key_id),
            )
            .outerjoin(ancestor_mode, ancestor_mode.id == ancestor.mode_id)
            .outerjoin(AppUser, AppUser.cern_login == key.created_by)
            .outerjoin(decommissioner, decommissioner.cern_login == key.decommissioned_by)
            .where(StagedEdit.id == key.staged_edit_id)
        )
    ).first()
    assert row is not None
    display_name, ancestor_mode_name, ancestor_version, ancestor_label, decommissioner_name = row
    assert display_name is not None
    retired_descendants = await _retired_descendants(key.id, session)
    return _build_key_detail(
        key,
        display_name,
        ancestor_mode_name,
        ancestor_version,
        ancestor_label,
        decommissioner_name,
        retired_descendants,
    )


_ChildRow = tuple[str, Key | None, int, str, str, str | None, str | None, str | None]


def _build_child_meta(row: _ChildRow) -> KeyChildMetaOut:
    """Unset child stays as a row with a null key, not skipped."""
    alias, key, namespace_id, namespace_name, subsystem_name, category, format_, mode_name = row
    return KeyChildMetaOut(
        id=key.id if key else None,
        alias=alias,
        label=key.label if key else None,
        namespace_id=namespace_id,
        namespace_name=namespace_name,
        subsystem_name=subsystem_name,
        category=category,
        format=format_,
        payload=key.payload if key and category == "external" else None,
        mode_name=mode_name,
        version=key.version if key else None,
        created_by=key.created_by if key else None,
        created_at=key.created_at if key else None,
        comment=key.comment if key else None,
    )


async def _child_level(
    parent_key_id: int, parent_namespace_id: int, session: SessionDep
) -> list[_ChildRow]:
    """One row per alias declared on the parent namespace, whether emptied or not."""
    child = aliased(Key)

    rows = await session.execute(
        select(
            NamespaceEdge.alias,
            child,
            Namespace.id,
            Namespace.name,
            Subsystem.name,
            Namespace.category,
            Namespace.format,
            Mode.name,
        )
        .select_from(NamespaceEdge)
        .join(Namespace, Namespace.id == NamespaceEdge.child_namespace_id)
        .join(Subsystem, Subsystem.id == Namespace.subsystem_id)
        .outerjoin(
            KeyChild,
            (KeyChild.parent_key_id == parent_key_id) & (KeyChild.alias == NamespaceEdge.alias),
        )
        .outerjoin(child, child.id == KeyChild.child_key_id)
        .outerjoin(Mode, Mode.id == child.mode_id)
        .where(NamespaceEdge.parent_namespace_id == parent_namespace_id)
        .order_by(NamespaceEdge.alias)
    )

    return [cast("_ChildRow", row) for row in rows.tuples()]


@router.get("/{subsystem_name}/{namespace_name}/{mode_name}/{version}/children")
async def get_key_children(
    subsystem_name: str,
    namespace_name: str,
    mode_name: str,
    version: KeyVersion,
    session: SessionDep,
) -> list[KeyChildMetaOut]:
    """One level of a bundle: one row per alias, whether emptied or not."""
    parent = await key_or_404(subsystem_name, namespace_name, mode_name, version, session)
    rows = await _child_level(parent.id, parent.namespace_id, session)
    return [_build_child_meta(row) for row in rows]


async def _build_aggregate(
    alias: str | None, key: Key, format_: str | None, ancestors: frozenset[int], session: SessionDep
) -> AggregateOut:
    node = AggregateOut(alias=alias, label=key.label, format=format_, payload=key.payload)
    if key.id in ancestors:
        return node
    seen = ancestors | {key.id}
    # Descends every node regardless of category, since category doesn't preclude child edges.
    # ponytail: one query per node; batch per depth level if this gets slow
    for (
        child_alias,
        child,
        _namespace_id,
        _namespace_name,
        _subsystem_name,
        _category,
        child_format,
        _mode_name,
    ) in await _child_level(key.id, key.namespace_id, session):
        node.children.append(
            AggregateOut(alias=child_alias, label=None, format=child_format, payload=None)
            if child is None
            else await _build_aggregate(child_alias, child, child_format, seen, session)
        )
    return node


@router.get("/{subsystem_name}/{namespace_name}/{mode_name}/{version}/aggregate")
async def aggregate_key(
    subsystem_name: str,
    namespace_name: str,
    mode_name: str,
    version: KeyVersion,
    session: SessionDep,
) -> AggregateOut:
    """Every payload under a key, nested by alias, crossing subsystem boundaries freely."""
    root = await key_or_404(subsystem_name, namespace_name, mode_name, version, session)
    format_ = await session.scalar(
        select(Namespace.format).where(Namespace.id == root.namespace_id)
    )
    return await _build_aggregate(None, root, format_, frozenset(), session)
