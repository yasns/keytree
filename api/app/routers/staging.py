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
from app.db.models import (
    Changeset,
    Key,
    Mode,
    Namespace,
    StagedArchival,
    StagedDecommission,
    StagedEdit,
    Subsystem,
)
from app.routers.keys import key_ancestry, key_or_404, keys_by_locator
from app.routers.user import upsert_app_user

router = APIRouter(
    prefix="/staging",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["staging"],
)


class StagedEditIn(BaseModel):
    subsystem_name: str
    namespace_name: str
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


class DecommissionIn(BaseModel):
    key_id: int


class ProposedChildOut(BaseModel):
    key_id: int
    mode_name: str
    version: int
    label: str


class StagedEditOut(BaseModel):
    id: int
    subsystem_name: str
    namespace_name: str
    mode_name: str
    base_version: int | None
    """Not necessarily the mode's tip. None for a forked mode's v1."""
    expected_version: int
    category: str | None
    visible: bool
    """False for edits on external leaf namespaces, which the UI hides from the changes list."""
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
    namespace_name: str
    mode_name: str
    archived: bool


class StagedDecommissionOut(BaseModel):
    key_id: int
    subsystem_name: str
    namespace_name: str
    mode_name: str
    version: int
    label: str
    decommissioned: bool


class ChangesetOut(BaseModel):
    id: int
    created_by: str
    created_at: datetime
    edits: list[StagedEditOut]
    archivals: list[StagedArchivalOut]
    decommissions: list[StagedDecommissionOut]


_EditRow = tuple[StagedEdit, str, str, str, int | None, str | None]
_ArchivalRow = tuple[StagedArchival, str, str, str]
_DecommissionRow = tuple[StagedDecommission, str, str, str, int, str]


def _concrete_children(proposed_children: object) -> set[int]:
    """Child key ids actually pinned; a `None` value means this changeset supplies that child."""
    children = cast("dict[str, int | None]", proposed_children or {})
    return {key_id for key_id in children.values() if key_id is not None}


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
    decommission_rows: list[_DecommissionRow],
) -> ChangesetOut:
    return ChangesetOut(
        id=changeset.id,
        created_by=changeset.created_by,
        created_at=changeset.created_at,
        archivals=[
            StagedArchivalOut(
                mode_id=archival.mode_id,
                subsystem_name=subsystem_name,
                namespace_name=namespace_name,
                mode_name=mode_name,
                archived=archival.archived,
            )
            for archival, subsystem_name, namespace_name, mode_name in archival_rows
        ],
        decommissions=[
            StagedDecommissionOut(
                key_id=decommission.key_id,
                subsystem_name=subsystem_name,
                namespace_name=namespace_name,
                mode_name=mode_name,
                version=version,
                label=label,
                decommissioned=decommission.decommissioned,
            )
            for decommission, subsystem_name, namespace_name, mode_name, version, label in (
                decommission_rows
            )
        ],
        edits=[
            StagedEditOut(
                id=edit.id,
                subsystem_name=subsystem_name,
                namespace_name=namespace_name,
                mode_name=mode_name,
                base_version=base_version,
                expected_version=edit.expected_version,
                category=category,
                visible=category != "external",
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
            for edit, subsystem_name, namespace_name, mode_name, base_version, category in rows
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

    stmt = insert(Changeset).values(created_by=cern_login)
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
        .join(Namespace, Namespace.id == Mode.namespace_id)
        .join(Subsystem, Subsystem.id == Namespace.subsystem_id)
    )


async def _edit_rows(changeset_id: int, session: SessionDep) -> list[_EditRow]:
    rows = await session.execute(
        join_mode_names(
            select(
                StagedEdit,
                Subsystem.name,
                Namespace.name,
                Mode.name,
                Key.version,
                Namespace.category,
            ),
            StagedEdit.mode_id,
        )
        .outerjoin(Key, Key.id == StagedEdit.base_key_id)
        .where(StagedEdit.changeset_id == changeset_id)
    )
    return list(rows.tuples())


async def _child_modes(rows: list[_EditRow], session: SessionDep) -> dict[int, ProposedChildOut]:
    """Covers proposed children plus fork/copy/base key refs, in one query."""
    key_ids = {
        key_id for edit, *_ in rows for key_id in _concrete_children(edit.proposed_children)
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
            select(StagedArchival, Subsystem.name, Namespace.name, Mode.name),
            StagedArchival.mode_id,
        ).where(StagedArchival.changeset_id == changeset_id)
    )
    return list(rows.tuples())


async def _decommission_rows(changeset_id: int, session: SessionDep) -> list[_DecommissionRow]:
    rows = await session.execute(
        join_mode_names(
            select(
                StagedDecommission,
                Subsystem.name,
                Namespace.name,
                Mode.name,
                Key.version,
                Key.label,
            ).join(Key, Key.id == StagedDecommission.key_id),
            Key.mode_id,
        ).where(StagedDecommission.changeset_id == changeset_id)
    )
    return list(rows.tuples())


def effective_flag(staged: bool | None, committed: bool) -> bool:
    """Own-changeset staged toggle overriding committed state, when there is one."""
    return staged if staged is not None else committed


async def retired_key_labels(
    key_ids: set[int], changeset_id: int, session: SessionDep
) -> list[str]:
    """Labels retired by either cause, own-changeset staged toggles overriding committed state."""
    if not key_ids:
        return []
    rows = await session.execute(
        select(
            Key.label,
            Key.decommissioned_at,
            StagedDecommission.decommissioned,
            Mode.archived_at,
            StagedArchival.archived,
        )
        .select_from(Key)
        .join(Mode, Mode.id == Key.mode_id)
        .outerjoin(
            StagedDecommission,
            (StagedDecommission.changeset_id == changeset_id)
            & (StagedDecommission.key_id == Key.id),
        )
        .outerjoin(
            StagedArchival,
            (StagedArchival.changeset_id == changeset_id) & (StagedArchival.mode_id == Key.mode_id),
        )
        .where(Key.id.in_(key_ids))
    )
    labels = []
    for label, decommissioned_at, staged_dec, archived_at, staged_arch in rows.tuples():
        if effective_flag(staged_dec, decommissioned_at is not None):
            labels.append(f"{label} (decommissioned)")
        elif effective_flag(staged_arch, archived_at is not None):
            labels.append(f"{label} (mode archived)")
    return labels


async def blocking_edit_labels(
    rows: list[_EditRow], key_ids: set[int], mode_ids: set[int], session: SessionDep
) -> list[str]:
    """Staged edits in this changeset that are based on, or reference, the given keys or modes."""
    if not key_ids and not mode_ids:
        return []
    children = {edit.id: _concrete_children(edit.proposed_children) for edit, *_ in rows}

    child_modes: dict[int, int] = {}
    if mode_ids and (referenced := set[int]().union(*children.values())):
        modes = await session.execute(select(Key.id, Key.mode_id).where(Key.id.in_(referenced)))
        child_modes = {key_id: mode_id for key_id, mode_id in modes.tuples()}

    labels = []
    for edit, subsystem_name, namespace_name, mode_name, *_ in rows:
        refs = children[edit.id] | ({edit.base_key_id} if edit.base_key_id is not None else set())
        hits_mode = edit.mode_id in mode_ids or any(
            child_modes.get(key_id) in mode_ids for key_id in children[edit.id]
        )
        if refs & key_ids or hits_mode:
            labels.append(f"{subsystem_name}/{namespace_name}/{mode_name} v{edit.expected_version}")
    return labels


async def archived_labels(mode_ids: set[int], changeset_id: int, session: SessionDep) -> list[str]:
    """Labels effectively archived, own-changeset staged toggle overriding committed state."""
    if not mode_ids:
        return []
    rows = await session.execute(
        select(Subsystem.name, Namespace.name, Mode.name, Mode.archived_at, StagedArchival.archived)
        .select_from(Mode)
        .join(Namespace, Namespace.id == Mode.namespace_id)
        .join(Subsystem, Subsystem.id == Namespace.subsystem_id)
        .outerjoin(
            StagedArchival,
            (StagedArchival.changeset_id == changeset_id) & (StagedArchival.mode_id == Mode.id),
        )
        .where(Mode.id.in_(mode_ids))
    )
    labels = []
    for subsystem_name, namespace_name, mode_name, archived_at, staged in rows.tuples():
        if effective_flag(staged, archived_at is not None):
            labels.append(f"{subsystem_name}/{namespace_name}/{mode_name}")
    return labels


async def changeset_out(
    changeset: Changeset, session: SessionDep, rows: list[_EditRow] | None = None
) -> ChangesetOut:
    if rows is None:
        rows = await _edit_rows(changeset.id, session)
    archival_rows = await _archival_rows(changeset.id, session)
    decommission_rows = await _decommission_rows(changeset.id, session)
    return _build_changeset(
        changeset, rows, await _child_modes(rows, session), archival_rows, decommission_rows
    )


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


def _baseline_id(base: _ResolvedBase) -> int | None:
    return base.base_key_id if base.base_key_id is not None else base.copied_from_key_id


async def _resolve_bases(
    edits: list[StagedEditIn], changeset_id: int, session: SessionDep
) -> list[_ResolvedBase]:
    """In request order."""
    locators = [(e.subsystem_name, e.namespace_name, e.mode_name, e.base_version) for e in edits]
    keys = await keys_by_locator(locators, session)

    unresolved = [e for e, locator in zip(edits, locators, strict=True) if locator not in keys]
    mode_ids_by_name: dict[tuple[str, str, str], int] = {}
    if unresolved:
        names = {(e.subsystem_name, e.namespace_name, e.mode_name) for e in unresolved}
        rows = await session.execute(
            select(Subsystem.name, Namespace.name, Mode.name, Mode.id)
            .select_from(Mode)
            .join(Namespace, Namespace.id == Mode.namespace_id)
            .join(Subsystem, Subsystem.id == Namespace.subsystem_id)
            .where(tuple_(Subsystem.name, Namespace.name, Mode.name).in_(names))
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
        key_name = (edit_in.subsystem_name, edit_in.namespace_name, edit_in.mode_name)
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

    check_ids = {base.base_key_id for base in bases if base.base_key_id is not None}
    for edit_in in edits:
        check_ids |= _concrete_children(edit_in.proposed_children)
    if retired := await retired_key_labels(check_ids, changeset.id, session):
        raise HTTPException(
            status_code=400,
            detail=f"cannot use retired key(s): {', '.join(sorted(retired))}",
        )

    if archived := await archived_labels({base.mode_id for base in bases}, changeset.id, session):
        raise HTTPException(
            status_code=400,
            detail=f"cannot edit archived mode(s): {', '.join(sorted(archived))}",
        )

    _ = await session.execute(
        delete(StagedEdit).where(
            StagedEdit.changeset_id == changeset.id,
            StagedEdit.mode_id.in_({base.mode_id for base in bases}),
        )
    )

    baseline_ids = {bid for base in bases if (bid := _baseline_id(base)) is not None}
    baseline_payloads, baseline_children = await key_ancestry(baseline_ids, session)

    for edit_in, base in zip(edits, bases, strict=True):
        baseline_key_id = _baseline_id(base)
        if baseline_key_id is not None:
            if edit_in.proposed_payload == baseline_payloads.get(baseline_key_id) and (
                edit_in.proposed_children or {}
            ) == baseline_children.get(baseline_key_id, {}):
                continue  # re-staged to the exact baseline: leave it undone
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


async def _guard_referenced(
    rows: list[_EditRow],
    ends_retired: bool,
    key_ids: set[int],
    mode_ids: set[int],
    subject: str,
    session: SessionDep,
) -> None:
    if not ends_retired:
        return
    if blocking := await blocking_edit_labels(rows, key_ids, mode_ids, session):
        raise HTTPException(
            status_code=400,
            detail=f"cannot {subject} referenced by staged edit(s): {', '.join(sorted(blocking))}",
        )


@router.post("/archive")
async def toggle_archival(body: ArchivalIn, request: Request, session: SessionDep) -> ChangesetOut:
    """Stages a mode's archive/unarchive, flipped from current state. A second toggle cancels it."""
    claims = request.state.claims
    cern_login = claims["cern_upn"]
    await upsert_app_user(claims, session)

    mode_row = (
        await session.execute(
            select(Mode, Subsystem.name)
            .join(Namespace, Namespace.id == Mode.namespace_id)
            .join(Subsystem, Subsystem.id == Namespace.subsystem_id)
            .where(Mode.id == body.mode_id)
        )
    ).first()
    if mode_row is None:
        raise HTTPException(status_code=404, detail="mode not found")
    mode, subsystem_name = mode_row

    await require_writable({subsystem_name}, claims, session)

    changeset = await _get_or_create_open_changeset(cern_login, session)

    rows = await _edit_rows(changeset.id, session)
    existing = await session.get(StagedArchival, (changeset.id, body.mode_id))
    # Cancelling reverts to committed state, so either branch can be the one that ends up archived.
    ends_archived = (mode.archived_at is not None) == (existing is not None)
    await _guard_referenced(rows, ends_archived, set(), {body.mode_id}, "archive a mode", session)

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
    return await changeset_out(changeset, session, rows)


@router.post("/decommission")
async def toggle_decommission(
    body: DecommissionIn, request: Request, session: SessionDep
) -> ChangesetOut:
    """Stages a key's decommission/recommission; a second toggle cancels."""
    claims = request.state.claims
    cern_login = claims["cern_upn"]
    await upsert_app_user(claims, session)

    key_row = (
        await session.execute(
            select(Key, Subsystem.name)
            .join(Mode, Mode.id == Key.mode_id)
            .join(Namespace, Namespace.id == Mode.namespace_id)
            .join(Subsystem, Subsystem.id == Namespace.subsystem_id)
            .where(Key.id == body.key_id)
        )
    ).first()
    if key_row is None:
        raise HTTPException(status_code=404, detail="key not found")
    key, subsystem_name = key_row

    await require_writable({subsystem_name}, claims, session)

    changeset = await _get_or_create_open_changeset(cern_login, session)

    rows = await _edit_rows(changeset.id, session)
    existing = await session.get(StagedDecommission, (changeset.id, body.key_id))
    # Cancelling reverts to committed state, so either branch can be the one that ends up retired.
    ends_retired = (key.decommissioned_at is not None) == (existing is not None)
    await _guard_referenced(rows, ends_retired, {body.key_id}, set(), "decommission a key", session)

    if existing is not None:
        await session.delete(existing)
    else:
        session.add(
            StagedDecommission(
                changeset_id=changeset.id,
                key_id=body.key_id,
                decommissioned=key.decommissioned_at is None,
            )
        )

    await session.commit()
    return await changeset_out(changeset, session, rows)


async def _login_and_source(
    body: StagedEditIn, request: Request, session: SessionDep
) -> tuple[str, Key]:
    claims = request.state.claims
    cern_login = claims["cern_upn"]
    await require_writable({body.subsystem_name}, claims, session)
    await upsert_app_user(claims, session)
    source = await key_or_404(
        body.subsystem_name, body.namespace_name, body.mode_name, body.base_version, session
    )
    return cern_login, source


async def _guard_retired_refs(
    body: StagedEditIn, source: Key, changeset_id: int, session: SessionDep
) -> None:
    """Fork/copy guard: a decommissioned source may not seed content, nor retired keys be pinned."""
    # An archived source stays allowed: forking is the only migration path off a frozen mode.
    staged = await session.get(StagedDecommission, (changeset_id, source.id))
    staged_flag = staged.decommissioned if staged is not None else None
    if effective_flag(staged_flag, source.decommissioned_at is not None):
        raise HTTPException(
            status_code=400, detail=f"cannot use decommissioned source key: {source.label}"
        )
    if retired := await retired_key_labels(
        _concrete_children(body.proposed_children), changeset_id, session
    ):
        raise HTTPException(
            status_code=400, detail=f"cannot use retired key(s): {', '.join(sorted(retired))}"
        )


@router.post("/fork")
async def fork_mode(body: ForkIn, request: Request, session: SessionDep) -> ChangesetOut:
    """Branches a key's content into a brand new mode on the same namespace, staged as its v1."""
    cern_login, source = await _login_and_source(body, request, session)

    namespace = await session.get(Namespace, source.namespace_id)
    assert namespace is not None

    changeset = await _get_or_create_open_changeset(cern_login, session)

    await _guard_retired_refs(body, source, changeset.id, session)

    mode = Mode(
        namespace_id=source.namespace_id,
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
        select(Mode).where(
            Mode.namespace_id == source.namespace_id, Mode.name == body.target_mode_name
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="target mode not found")

    changeset = await _get_or_create_open_changeset(cern_login, session)

    if await archived_labels({target.id}, changeset.id, session):
        raise HTTPException(status_code=400, detail="target mode is archived")

    await _guard_retired_refs(body, source, changeset.id, session)

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


async def _delete_orphan_modes(cern_login: str, session: SessionDep) -> None:
    """Modes created while forking that no longer have any staged or committed content."""
    _ = await session.execute(
        delete(Mode).where(
            Mode.created_by == cern_login,
            ~select(Key.id).where(Key.mode_id == Mode.id).exists(),
            ~select(StagedEdit.id).where(StagedEdit.mode_id == Mode.id).exists(),
            ~select(StagedArchival.mode_id).where(StagedArchival.mode_id == Mode.id).exists(),
        )
    )


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
    await _delete_orphan_modes(cern_login, session)
    await session.commit()


@router.delete("/edits/{edit_id}", status_code=204)
async def discard_edit(edit_id: int, request: Request, session: SessionDep) -> None:
    """Discards one staged edit, keeping the rest of the changeset intact."""
    cern_login = request.state.claims["cern_upn"]
    changeset = await open_changeset(cern_login, session)
    if changeset is None:
        raise HTTPException(status_code=404, detail="no open changeset")
    result = await session.execute(
        delete(StagedEdit)
        .where(StagedEdit.id == edit_id, StagedEdit.changeset_id == changeset.id)
        .returning(StagedEdit.base_key_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="staged edit not found")
    if row[0] is None:  # was a fork's v1 edit: its mode may now be orphaned
        await _delete_orphan_modes(cern_login, session)
    await session.commit()
