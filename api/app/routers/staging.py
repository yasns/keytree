from datetime import datetime
from typing import Any, Literal, NamedTuple, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ColumnElement, Select, delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute
from tsgauth.fastapi import JWTBearerClaims

from app.authz import require_writable
from app.db.base import SessionDep
from app.db.models import Changeset, Key, Mode, Node, StagedArchival, StagedEdit, Subsystem
from app.routers.keys import key_or_404, keys_by_locator
from app.routers.user import upsert_app_user

router = APIRouter(
    prefix="/staging",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["staging"],
)


class StagedEditIn(BaseModel):
    subsystem_name: str
    node_name: str
    mode_name: str
    base_version: int
    proposed_payload: str | None = None
    proposed_children: dict[str, int | None] | None = None
    """alias -> child key id, or None if this changeset should produce the key."""
    comment: str
    validation_status: Literal["skipped", "passed", "failed"] = "skipped"

    @model_validator(mode="after")
    def _proposes_something(self) -> "StagedEditIn":
        if self.proposed_payload is None and self.proposed_children is None:
            raise ValueError("staged edit must propose a payload or children")
        return self


class ForkIn(StagedEditIn):
    new_mode_name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    description: str = Field(min_length=1, max_length=255)


class CopyIn(StagedEditIn):
    target_mode_name: str


class ArchivalIn(BaseModel):
    mode_id: int


class ProposedChildOut(BaseModel):
    key_id: int
    mode_name: str
    version: int
    label: str


class StagedEditOut(BaseModel):
    id: int
    subsystem_name: str
    node_name: str
    mode_name: str
    base_version: int | None
    """Not necessarily the mode's tip. None for a forked mode's v1."""
    expected_version: int
    category: str | None
    proposed_payload: str | None
    proposed_children: dict[str, ProposedChildOut | None] | None
    copied_from: ProposedChildOut | None
    based_on: ProposedChildOut | None
    """The fork/copy source, or its previous version otherwise."""
    comment: str
    created_by: str
    validation_status: str


class StagedArchivalOut(BaseModel):
    mode_id: int
    subsystem_name: str
    node_name: str
    mode_name: str
    archived: bool


class ChangesetOut(BaseModel):
    id: int
    comment: str
    created_by: str
    created_at: datetime
    edits: list[StagedEditOut]
    archivals: list[StagedArchivalOut]


_EditRow = tuple[StagedEdit, str, str, str, int | None, str | None]
_ArchivalRow = tuple[StagedArchival, str, str, str]


def _build_children(
    proposed_children: object, child_modes: dict[int, ProposedChildOut]
) -> dict[str, ProposedChildOut | None] | None:
    if proposed_children is None:
        return None
    children = cast("dict[str, int | None]", proposed_children)
    return {
        alias: None if key_id is None else child_modes[key_id] for alias, key_id in children.items()
    }


def _build_changeset(
    changeset: Changeset,
    rows: list[_EditRow],
    child_modes: dict[int, ProposedChildOut],
    archival_rows: list[_ArchivalRow],
) -> ChangesetOut:
    return ChangesetOut(
        id=changeset.id,
        comment=changeset.comment,
        created_by=changeset.created_by,
        created_at=changeset.created_at,
        archivals=[
            StagedArchivalOut(
                mode_id=archival.mode_id,
                subsystem_name=subsystem_name,
                node_name=node_name,
                mode_name=mode_name,
                archived=archival.archived,
            )
            for archival, subsystem_name, node_name, mode_name in archival_rows
        ],
        edits=[
            StagedEditOut(
                id=edit.id,
                subsystem_name=subsystem_name,
                node_name=node_name,
                mode_name=mode_name,
                base_version=base_version,
                expected_version=edit.expected_version,
                category=category,
                proposed_payload=edit.proposed_payload,
                proposed_children=_build_children(edit.proposed_children, child_modes),
                copied_from=child_modes.get(edit.copied_from_key_id)
                if edit.copied_from_key_id is not None
                else None,
                based_on=child_modes.get(aid)
                if (aid := edit.copied_from_key_id or edit.base_key_id) is not None
                else None,
                comment=edit.comment,
                created_by=changeset.created_by,
                validation_status=edit.validation_status,
            )
            for edit, subsystem_name, node_name, mode_name, base_version, category in rows
        ],
    )


async def open_changeset(cern_login: str, session: SessionDep) -> Changeset | None:
    return await session.scalar(
        select(Changeset).where(
            Changeset.created_by == cern_login, Changeset.committed_at.is_(None)
        )
    )


async def _get_or_create_open_changeset(cern_login: str, session: SessionDep) -> Changeset:
    changeset = await open_changeset(cern_login, session)
    if changeset is not None:
        return changeset

    stmt = insert(Changeset).values(created_by=cern_login, comment="")
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[Changeset.created_by], index_where=Changeset.committed_at.is_(None)
    )
    _ = await session.execute(stmt)
    await session.commit()
    changeset = await open_changeset(cern_login, session)
    assert changeset is not None
    return changeset


def join_mode_names(
    stmt: Select[Any], mode_id: ColumnElement[int] | InstrumentedAttribute[int]
) -> Select[Any]:
    """mode_id can be any FK column pointing at Mode.id."""
    return (
        stmt.join(Mode, Mode.id == mode_id)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
    )


async def _edit_rows(changeset_id: int, session: SessionDep) -> list[_EditRow]:
    rows = await session.execute(
        join_mode_names(
            select(StagedEdit, Subsystem.name, Node.name, Mode.name, Key.version, Node.category),
            StagedEdit.mode_id,
        )
        .outerjoin(Key, Key.id == StagedEdit.base_key_id)
        .where(StagedEdit.changeset_id == changeset_id)
    )
    return list(rows.tuples())


async def _child_modes(rows: list[_EditRow], session: SessionDep) -> dict[int, ProposedChildOut]:
    """Covers proposed children plus fork/copy/base key refs, in one query."""
    key_ids = {
        key_id
        for edit, *_ in rows
        for key_id in cast("dict[str, int | None]", edit.proposed_children or {}).values()
        if key_id is not None
    } | {edit.copied_from_key_id for edit, *_ in rows if edit.copied_from_key_id is not None}
    key_ids |= {edit.base_key_id for edit, *_ in rows if edit.base_key_id is not None}
    if not key_ids:
        return {}
    rows_ = await session.execute(
        select(Key.id, Mode.name, Key.version, Key.label)
        .join(Mode, Mode.id == Key.mode_id)
        .where(Key.id.in_(key_ids))
    )
    return {
        key_id: ProposedChildOut(key_id=key_id, mode_name=mode_name, version=version, label=label)
        for key_id, mode_name, version, label in rows_.tuples()
    }


async def _archival_rows(changeset_id: int, session: SessionDep) -> list[_ArchivalRow]:
    rows = await session.execute(
        join_mode_names(
            select(StagedArchival, Subsystem.name, Node.name, Mode.name), StagedArchival.mode_id
        ).where(StagedArchival.changeset_id == changeset_id)
    )
    return list(rows.tuples())


async def changeset_out(changeset: Changeset, session: SessionDep) -> ChangesetOut:
    rows = await _edit_rows(changeset.id, session)
    archival_rows = await _archival_rows(changeset.id, session)
    return _build_changeset(changeset, rows, await _child_modes(rows, session), archival_rows)


async def _tip_keys(mode_ids: set[int], session: SessionDep) -> dict[int, tuple[int, int]]:
    """Modes with no keys yet are absent from the result."""
    rows = await session.execute(
        select(Key.mode_id, Key.id, Key.version)
        .where(Key.mode_id.in_(mode_ids))
        .order_by(Key.mode_id, Key.version.desc())
        .distinct(Key.mode_id)
    )
    return {mode_id: (key_id, version) for mode_id, key_id, version in rows.tuples()}


@router.get("/")
async def get_changeset(request: Request, session: SessionDep) -> ChangesetOut | None:
    """Fetches the caller's open changeset and its staged edits, or null if none is open."""
    changeset = await open_changeset(request.state.claims["cern_upn"], session)
    if changeset is None:
        return None
    return await changeset_out(changeset, session)


class _ResolvedBase(NamedTuple):
    mode_id: int
    base_key_id: int | None
    expected_version: int
    copied_from_key_id: int | None


async def _resolve_bases(
    edits: list[StagedEditIn], changeset_id: int, session: SessionDep
) -> list[_ResolvedBase]:
    """In request order."""
    locators = [(e.subsystem_name, e.node_name, e.mode_name, e.base_version) for e in edits]
    keys = await keys_by_locator(locators, session)

    unresolved = [e for e, locator in zip(edits, locators, strict=True) if locator not in keys]
    mode_ids_by_name: dict[tuple[str, str, str], int] = {}
    if unresolved:
        names = {(e.subsystem_name, e.node_name, e.mode_name) for e in unresolved}
        rows = await session.execute(
            select(Subsystem.name, Node.name, Mode.name, Mode.id)
            .select_from(Mode)
            .join(Node, Node.id == Mode.node_id)
            .join(Subsystem, Subsystem.id == Node.subsystem_id)
            .where(tuple_(Subsystem.name, Node.name, Mode.name).in_(names))
        )
        mode_ids_by_name = {(s, n, m): mode_id for s, n, m, mode_id in rows.tuples()}

    keyless_mode_ids = set(mode_ids_by_name.values())
    own_edits: dict[int, StagedEdit] = {}
    if keyless_mode_ids:
        rows = await session.execute(
            select(StagedEdit).where(
                StagedEdit.changeset_id == changeset_id,
                StagedEdit.mode_id.in_(keyless_mode_ids),
            )
        )
        own_edits = {edit.mode_id: edit for edit in rows.scalars()}

    tips = await _tip_keys({key.mode_id for key in keys.values()}, session)

    bases: list[_ResolvedBase] = []
    for edit_in, locator in zip(edits, locators, strict=True):
        key = keys.get(locator)
        if key is not None:
            bases.append(_ResolvedBase(key.mode_id, key.id, tips[key.mode_id][1] + 1, None))
            continue
        key_name = (edit_in.subsystem_name, edit_in.node_name, edit_in.mode_name)
        mode_id = mode_ids_by_name.get(key_name)
        own = own_edits.get(mode_id) if mode_id is not None else None
        if mode_id is None or own is None or own.expected_version != edit_in.base_version:
            raise HTTPException(status_code=404, detail="key not found")
        bases.append(
            _ResolvedBase(mode_id, own.base_key_id, own.expected_version, own.copied_from_key_id)
        )
    return bases


@router.post("/")
async def stage_edits(
    edits: list[StagedEditIn], request: Request, session: SessionDep
) -> ChangesetOut:
    """Stages (or re-stages) a set of edits in the caller's open changeset."""
    claims = request.state.claims
    cern_login = claims["cern_upn"]

    await require_writable({e.subsystem_name for e in edits}, claims, session)

    await upsert_app_user(claims, session)

    changeset = await _get_or_create_open_changeset(cern_login, session)

    bases = await _resolve_bases(edits, changeset.id, session)

    _ = await session.execute(
        delete(StagedEdit).where(
            StagedEdit.changeset_id == changeset.id,
            StagedEdit.mode_id.in_({base.mode_id for base in bases}),
        )
    )

    for edit_in, base in zip(edits, bases, strict=True):
        session.add(
            StagedEdit(
                changeset_id=changeset.id,
                mode_id=base.mode_id,
                base_key_id=base.base_key_id,
                copied_from_key_id=base.copied_from_key_id,
                expected_version=base.expected_version,
                proposed_payload=edit_in.proposed_payload,
                proposed_children=edit_in.proposed_children,
                comment=edit_in.comment,
                validation_status=edit_in.validation_status,
            )
        )

    await session.commit()
    return await changeset_out(changeset, session)


@router.post("/archive")
async def toggle_archival(body: ArchivalIn, request: Request, session: SessionDep) -> ChangesetOut:
    """Stages a mode's archive/unarchive, flipped from current state. A second toggle cancels it."""
    claims = request.state.claims
    cern_login = claims["cern_upn"]
    await upsert_app_user(claims, session)

    mode_row = (
        await session.execute(
            select(Mode, Subsystem.name)
            .join(Node, Node.id == Mode.node_id)
            .join(Subsystem, Subsystem.id == Node.subsystem_id)
            .where(Mode.id == body.mode_id)
        )
    ).first()
    if mode_row is None:
        raise HTTPException(status_code=404, detail="mode not found")
    mode, subsystem_name = mode_row

    await require_writable({subsystem_name}, claims, session)

    changeset = await _get_or_create_open_changeset(cern_login, session)

    existing = await session.get(StagedArchival, (changeset.id, body.mode_id))
    if existing is not None:
        await session.delete(existing)
    else:
        session.add(
            StagedArchival(
                changeset_id=changeset.id,
                mode_id=body.mode_id,
                archived=mode.archived_at is None,
            )
        )

    await session.commit()
    return await changeset_out(changeset, session)


async def _login_and_source(
    body: StagedEditIn, request: Request, session: SessionDep
) -> tuple[str, Key]:
    claims = request.state.claims
    cern_login = claims["cern_upn"]
    await require_writable({body.subsystem_name}, claims, session)
    await upsert_app_user(claims, session)
    source = await key_or_404(
        body.subsystem_name, body.node_name, body.mode_name, body.base_version, session
    )
    return cern_login, source


@router.post("/fork")
async def fork_mode(body: ForkIn, request: Request, session: SessionDep) -> ChangesetOut:
    """Branches a key's content into a brand new mode on the same node, staged as its v1."""
    cern_login, source = await _login_and_source(body, request, session)

    node = await session.get(Node, source.node_id)
    assert node is not None

    changeset = await _get_or_create_open_changeset(cern_login, session)

    mode = Mode(
        node_id=source.node_id,
        name=body.new_mode_name,
        description=body.description,
        forked_from_key_id=source.id,
        created_by=cern_login,
    )
    session.add(mode)
    try:
        await session.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="mode already exists") from e

    session.add(
        StagedEdit(
            changeset_id=changeset.id,
            mode_id=mode.id,
            base_key_id=None,
            copied_from_key_id=source.id,
            expected_version=1,
            proposed_payload=body.proposed_payload,
            proposed_children=body.proposed_children,
            comment=body.comment,
            validation_status=body.validation_status,
        )
    )

    await session.commit()
    return await changeset_out(changeset, session)


@router.post("/copy")
async def copy_to_mode(body: CopyIn, request: Request, session: SessionDep) -> ChangesetOut:
    """Copies a key's content onto another existing mode, staged as that mode's next version."""
    cern_login, source = await _login_and_source(body, request, session)

    target = await session.scalar(
        select(Mode).where(Mode.node_id == source.node_id, Mode.name == body.target_mode_name)
    )
    if target is None:
        raise HTTPException(status_code=404, detail="target mode not found")

    changeset = await _get_or_create_open_changeset(cern_login, session)

    # staged archival on target overrides its committed state
    staged_archival = await session.get(StagedArchival, (changeset.id, target.id))
    effective_archived = (
        staged_archival.archived if staged_archival is not None else target.archived_at is not None
    )
    if effective_archived:
        raise HTTPException(status_code=400, detail="target mode is archived")

    _ = await session.execute(
        delete(StagedEdit).where(
            StagedEdit.changeset_id == changeset.id, StagedEdit.mode_id == target.id
        )
    )
    tip_key_id, tip_version = (await _tip_keys({target.id}, session)).get(target.id, (None, 0))
    session.add(
        StagedEdit(
            changeset_id=changeset.id,
            mode_id=target.id,
            base_key_id=tip_key_id,
            copied_from_key_id=source.id,
            expected_version=tip_version + 1,
            proposed_payload=body.proposed_payload,
            proposed_children=body.proposed_children,
            comment=body.comment,
            validation_status=body.validation_status,
        )
    )

    await session.commit()
    return await changeset_out(changeset, session)


@router.delete("/", status_code=204)
async def discard_changeset(request: Request, session: SessionDep) -> None:
    """Discards the caller's open changeset and all its staged edits, including any modes created
    while forking."""
    cern_login = request.state.claims["cern_upn"]
    _ = await session.execute(
        delete(Changeset).where(
            Changeset.created_by == cern_login, Changeset.committed_at.is_(None)
        )
    )
    _ = await session.execute(
        delete(Mode).where(
            Mode.created_by == cern_login,
            ~select(Key.id).where(Key.mode_id == Mode.id).exists(),
            ~select(StagedEdit.id).where(StagedEdit.mode_id == Mode.id).exists(),
            ~select(StagedArchival.mode_id).where(StagedArchival.mode_id == Mode.id).exists(),
        )
    )
    await session.commit()
