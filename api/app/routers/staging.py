from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import Changeset, Key, Mode, Node, StagedEdit, Subsystem
from app.routers.keys import keys_or_404
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

    @model_validator(mode="after")
    def _proposes_something(self) -> "StagedEditIn":
        if self.proposed_payload is None and self.proposed_children is None:
            raise ValueError("staged edit must propose a payload or children")
        return self


class ProposedChildOut(BaseModel):
    key_id: int
    mode_name: str
    version: int


class StagedEditOut(BaseModel):
    id: int
    subsystem_name: str
    node_name: str
    mode_name: str
    base_version: int
    """Version whose content this edit started from, which need not be the mode's tip."""
    expected_version: int
    """Version the commit will create."""
    category: str | None
    proposed_payload: str | None
    proposed_children: dict[str, ProposedChildOut | None] | None
    comment: str
    created_by: str
    created_at: datetime


class ChangesetOut(BaseModel):
    id: int
    comment: str
    created_by: str
    created_at: datetime
    edits: list[StagedEditOut]


_EditRow = tuple[StagedEdit, str, str, str, int, str | None]


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
    changeset: Changeset, rows: list[_EditRow], child_modes: dict[int, ProposedChildOut]
) -> ChangesetOut:
    return ChangesetOut(
        id=changeset.id,
        comment=changeset.comment,
        created_by=changeset.created_by,
        created_at=changeset.created_at,
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
                comment=edit.comment,
                created_by=changeset.created_by,
                created_at=edit.created_at,
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


async def _edit_rows(changeset_id: int, session: SessionDep) -> list[_EditRow]:
    rows = await session.execute(
        select(StagedEdit, Subsystem.name, Node.name, Mode.name, Key.version, Node.category)
        .join(Mode, Mode.id == StagedEdit.mode_id)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .join(Key, Key.id == StagedEdit.base_key_id)
        .where(StagedEdit.changeset_id == changeset_id)
    )
    return list(rows.tuples())


async def _child_modes(rows: list[_EditRow], session: SessionDep) -> dict[int, ProposedChildOut]:
    """Mode name and version for every child key the given edits point at, in one query."""
    key_ids = {
        key_id
        for edit, *_ in rows
        for key_id in cast("dict[str, int | None]", edit.proposed_children or {}).values()
        if key_id is not None
    }
    if not key_ids:
        return {}
    rows_ = await session.execute(
        select(Key.id, Mode.name, Key.version)
        .join(Mode, Mode.id == Key.mode_id)
        .where(Key.id.in_(key_ids))
    )
    return {
        key_id: ProposedChildOut(key_id=key_id, mode_name=mode_name, version=version)
        for key_id, mode_name, version in rows_.tuples()
    }


async def changeset_out(changeset: Changeset, session: SessionDep) -> ChangesetOut:
    rows = await _edit_rows(changeset.id, session)
    return _build_changeset(changeset, rows, await _child_modes(rows, session))


async def _tip_versions(mode_ids: set[int], session: SessionDep) -> dict[int, int]:
    """Newest committed version per mode. Every mode id must already have at least one key."""
    rows = await session.execute(
        select(Key.mode_id, func.max(Key.version))
        .where(Key.mode_id.in_(mode_ids))
        .group_by(Key.mode_id)
    )
    return dict(rows.tuples().all())


@router.get("/")
async def get_changeset(request: Request, session: SessionDep) -> ChangesetOut | None:
    """Fetches the caller's open changeset and its staged edits, or null if none is open."""
    changeset = await open_changeset(request.state.claims["cern_upn"], session)
    if changeset is None:
        return None
    return await changeset_out(changeset, session)


@router.post("/")
async def stage_edits(
    edits: list[StagedEditIn], request: Request, session: SessionDep
) -> ChangesetOut:
    """Stages (or re-stages) a set of edits in the caller's open changeset."""
    claims = request.state.claims
    cern_login = claims["cern_upn"]

    await upsert_app_user(claims, session)

    changeset = await _get_or_create_open_changeset(cern_login, session)

    base_keys = await keys_or_404(
        [
            (edit_in.subsystem_name, edit_in.node_name, edit_in.mode_name, edit_in.base_version)
            for edit_in in edits
        ],
        session,
    )

    # Staged edits are immutable, so re-staging deletes then inserts.
    _ = await session.execute(
        delete(StagedEdit).where(
            StagedEdit.changeset_id == changeset.id,
            StagedEdit.mode_id.in_({key.mode_id for key in base_keys}),
        )
    )

    tips = await _tip_versions({key.mode_id for key in base_keys}, session)

    for edit_in, base_key in zip(edits, base_keys, strict=True):
        session.add(
            StagedEdit(
                changeset_id=changeset.id,
                mode_id=base_key.mode_id,
                base_key_id=base_key.id,
                expected_version=tips[base_key.mode_id] + 1,
                proposed_payload=edit_in.proposed_payload,
                proposed_children=edit_in.proposed_children,
                comment=edit_in.comment,
                validation_status="skipped",  # hardcoded until we have validation JSON Schemas
            )
        )

    await session.commit()
    return await changeset_out(changeset, session)


@router.delete("/", status_code=204)
async def discard_changeset(request: Request, session: SessionDep) -> None:
    """Discards the caller's open changeset and all its staged edits."""
    cern_login = request.state.claims["cern_upn"]
    _ = await session.execute(
        delete(Changeset).where(
            Changeset.created_by == cern_login, Changeset.committed_at.is_(None)
        )
    )
    await session.commit()
