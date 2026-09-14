from datetime import UTC, datetime
from typing import NamedTuple, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, tuple_
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import (
    Changeset,
    Key,
    KeyChild,
    Mode,
    Node,
    NodeEdge,
    StagedArchival,
    StagedEdit,
    Subsystem,
)
from app.routers.staging import ChangesetOut, changeset_out, join_mode_names, open_changeset

router = APIRouter(
    prefix="/commit",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["commit"],
)


class CommitIn(BaseModel):
    comment: str = Field(min_length=1, max_length=255)
    overwrite_conflicts: bool = False
    """Commit conflicting edits on top of the newer versions."""


class ConflictOut(BaseModel):
    """A staged edit whose target version was taken while it sat in the changeset."""

    subsystem_name: str
    node_name: str
    mode_name: str
    base_version: int | None
    expected_version: int
    tip_version: int


class _CommitRow(NamedTuple):
    edit: StagedEdit
    subsystem_name: str
    node_name: str
    mode_name: str
    node_id: int
    base_version: int | None
    tip_version: int


def _is_conflicted(row: _CommitRow) -> bool:
    """True once another commit has taken the target version since staging."""
    return row.edit.expected_version != row.tip_version + 1


def _conflicts(rows: list[_CommitRow]) -> list[ConflictOut]:
    return [
        ConflictOut(
            subsystem_name=row.subsystem_name,
            node_name=row.node_name,
            mode_name=row.mode_name,
            base_version=row.base_version,
            expected_version=row.edit.expected_version,
            tip_version=row.tip_version,
        )
        for row in rows
        if _is_conflicted(row)
    ]


def _build_keys(rows: list[_CommitRow], changeset: Changeset) -> list[Key]:
    """Always lands on the tip, regardless of the edit's base version."""
    keys: list[Key] = []
    for row in rows:
        version = row.tip_version + 1
        keys.append(
            Key(
                mode_id=row.edit.mode_id,
                node_id=row.node_id,
                version=version,
                label=f"{row.subsystem_name}/{row.node_name}/{row.mode_name}/v{version}",
                payload=row.edit.proposed_payload,
                staged_edit_id=row.edit.id,
                created_by=changeset.created_by,
                comment=row.edit.comment,
            )
        )
    return keys


def _build_key_children(
    rows: list[_CommitRow],
    keys: list[Key],
    child_node_of: dict[tuple[int, str], int],
    node_of_key: dict[int, int],
) -> list[KeyChild]:
    """None means the key this changeset produces for that alias's node; alias absent from map
    means cleared."""
    by_mode = {key.mode_id: key for key in keys}
    by_node = {key.node_id: key for key in keys}
    children: list[KeyChild] = []
    for row in rows:
        if row.edit.proposed_children is None:
            continue
        parent_key = by_mode[row.edit.mode_id]
        for alias, key_id in cast("dict[str, int | None]", row.edit.proposed_children).items():
            if key_id is None:
                child_node_id = child_node_of.get((row.node_id, alias))
                child_key = by_node.get(child_node_id) if child_node_id is not None else None
                if child_key is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"no key to fill '{alias}' on {parent_key.label}",
                    )
                child_key_id, resolved_child_node_id = child_key.id, child_node_id
            else:
                resolved_child_node_id = node_of_key.get(key_id)
                if resolved_child_node_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"no key {key_id} for '{alias}' on {parent_key.label}",
                    )
                child_key_id = key_id
            children.append(
                KeyChild(
                    parent_key_id=parent_key.id,
                    alias=alias,
                    child_key_id=child_key_id,
                    parent_node_id=row.node_id,
                    child_node_id=resolved_child_node_id,
                )
            )
    return children


def _archive_modes(
    archivals: list[StagedArchival], modes: dict[int, Mode], cern_login: str
) -> None:
    for archival in archivals:
        mode = modes[archival.mode_id]
        mode.archived_by = cern_login if archival.archived else None
        mode.archived_at = datetime.now(UTC) if archival.archived else None


async def _commit_rows(changeset_id: int, session: SessionDep) -> list[_CommitRow]:
    tip_versions = (
        select(Key.mode_id, func.max(Key.version).label("tip_version"))
        .where(
            Key.mode_id.in_(
                select(StagedEdit.mode_id).where(StagedEdit.changeset_id == changeset_id)
            )
        )
        .group_by(Key.mode_id)
        .subquery()
    )
    result = await session.execute(
        join_mode_names(
            select(
                StagedEdit,
                Subsystem.name,
                Node.name,
                Mode.name,
                Node.id,
                Key.version,
                func.coalesce(tip_versions.c.tip_version, 0),
            ),
            StagedEdit.mode_id,
        )
        .outerjoin(Key, Key.id == StagedEdit.base_key_id)
        .outerjoin(tip_versions, tip_versions.c.mode_id == StagedEdit.mode_id)
        .where(StagedEdit.changeset_id == changeset_id)
    )
    return [_CommitRow(*row) for row in result.tuples()]


def _proposed_child_refs(rows: list[_CommitRow]) -> tuple[set[tuple[int, str]], set[int]]:
    """(node_id, alias) pairs needing a NodeEdge lookup, and key ids needing a Key -> node_id
    lookup."""
    none_aliases: set[tuple[int, str]] = set()
    concrete_ids: set[int] = set()
    for row in rows:
        children = cast("dict[str, int | None]", row.edit.proposed_children or {})
        for alias, key_id in children.items():
            if key_id is None:
                none_aliases.add((row.node_id, alias))
            else:
                concrete_ids.add(key_id)
    return none_aliases, concrete_ids


def _rebased_edits(
    conflicted: list[_CommitRow], tip_keys: dict[int, tuple[int, int]]
) -> list[StagedEdit]:
    return [
        StagedEdit(
            changeset_id=row.edit.changeset_id,
            mode_id=row.edit.mode_id,
            base_key_id=tip_keys[row.edit.mode_id][0],
            copied_from_key_id=row.edit.copied_from_key_id,
            expected_version=tip_keys[row.edit.mode_id][1] + 1,
            proposed_payload=row.edit.proposed_payload,
            proposed_children=row.edit.proposed_children,
            comment=row.edit.comment,
            validation_status=row.edit.validation_status,
        )
        for row in conflicted
    ]


@router.post("/rebase")
async def rebase_changeset(request: Request, session: SessionDep) -> ChangesetOut:
    """Moves every conflicting edit onto the version committed since it was staged, keeping its
    proposed payload and children."""
    changeset = await open_changeset(request.state.claims["cern_upn"], session)
    if changeset is None:
        raise HTTPException(status_code=404, detail="no open changeset")

    rows = await _commit_rows(changeset.id, session)
    conflicted = [row for row in rows if _is_conflicted(row)]
    if not conflicted:
        return await changeset_out(changeset, session)

    key_rows = await session.execute(
        select(Key.mode_id, Key.id, Key.version).where(
            tuple_(Key.mode_id, Key.version).in_(
                {(row.edit.mode_id, row.tip_version) for row in conflicted}
            )
        )
    )
    tip_keys = {mode_id: (key_id, version) for mode_id, key_id, version in key_rows.tuples()}

    rebased = _rebased_edits(conflicted, tip_keys)
    _ = await session.execute(
        delete(StagedEdit).where(StagedEdit.id.in_({row.edit.id for row in conflicted}))
    )
    session.add_all(rebased)
    await session.commit()

    return await changeset_out(changeset, session)


@router.post(
    "/",
    status_code=204,
    responses={409: {"model": list[ConflictOut], "description": "Target versions taken since"}},
)
async def commit_changeset(body: CommitIn, request: Request, session: SessionDep) -> None:
    """Materialises every staged edit in the caller's open changeset as a key, then closes it."""
    claims = request.state.claims
    cern_login = claims["cern_upn"]

    changeset = await open_changeset(cern_login, session)
    if changeset is None:
        raise HTTPException(status_code=404, detail="no open changeset")

    rows = await _commit_rows(changeset.id, session)
    archivals = list(
        await session.scalars(
            select(StagedArchival).where(StagedArchival.changeset_id == changeset.id)
        )
    )
    if not rows and not archivals:
        raise HTTPException(status_code=400, detail="changeset has no staged edits")

    if not body.overwrite_conflicts and (conflicts := _conflicts(rows)):
        raise HTTPException(status_code=409, detail=[c.model_dump() for c in conflicts])

    keys = _build_keys(rows, changeset)
    session.add_all(keys)
    await session.flush()

    none_aliases, concrete_ids = _proposed_child_refs(rows)

    child_node_of: dict[tuple[int, str], int] = {}
    if none_aliases:
        edge_rows = await session.execute(
            select(NodeEdge.parent_node_id, NodeEdge.alias, NodeEdge.child_node_id).where(
                tuple_(NodeEdge.parent_node_id, NodeEdge.alias).in_(none_aliases)
            )
        )
        child_node_of = {(p, a): c for p, a, c in edge_rows.tuples()}

    node_of_key: dict[int, int] = {}
    if concrete_ids:
        id_rows = await session.execute(select(Key.id, Key.node_id).where(Key.id.in_(concrete_ids)))
        node_of_key = dict(id_rows.tuples().all())

    session.add_all(_build_key_children(rows, keys, child_node_of, node_of_key))

    if archivals:
        modes = {
            mode.id: mode
            for mode in await session.scalars(
                select(Mode).where(Mode.id.in_({a.mode_id for a in archivals}))
            )
        }
        _archive_modes(archivals, modes, cern_login)

    changeset.comment = body.comment
    changeset.committed_at = datetime.now(UTC)
    resource_access = cast("dict[str, object]", claims.get("resource_access", {}))
    keytree_access = cast("dict[str, object]", resource_access.get("keytree", {}))
    changeset.committed_with_roles = cast("list[str]", keytree_access.get("roles", []))

    await session.commit()
