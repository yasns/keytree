from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, model_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import Changeset, Key, Mode, Node, StagedEdit, Subsystem
from app.routers.keys import key_or_404
from app.routers.user import upsert_app_user

router = APIRouter(
    prefix="/changeset",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["changeset"],
)


class StagedEditIn(BaseModel):
    subsystem_name: str
    node_name: str
    mode_name: str
    base_version: int
    proposed_payload: str | None = None
    proposed_children: dict[str, int | None] | None = None
    """alias -> child key id, or None if this changeset should create the key."""
    comment: str

    @model_validator(mode="after")
    def _proposes_something(self) -> "StagedEditIn":
        if self.proposed_payload is None and self.proposed_children is None:
            raise ValueError("staged edit must propose a payload or children")
        return self


class ProposedChildOut(BaseModel):
    key_id: int
    mode_name: str
    """Child's mode can be rendered by the caller without a second lookup."""


class StagedEditOut(BaseModel):
    id: int
    subsystem_name: str
    node_name: str
    mode_name: str
    base_version: int
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
    proposed_children: object, child_modes: dict[int, str]
) -> dict[str, ProposedChildOut | None] | None:
    """Resolves an edit's stored alias -> key id map into alias -> (key id, mode name)."""
    if proposed_children is None:
        return None
    children = cast("dict[str, int | None]", proposed_children)
    return {
        alias: None
        if key_id is None
        else ProposedChildOut(key_id=key_id, mode_name=child_modes[key_id])
        for alias, key_id in children.items()
    }


def _build_changeset(
    changeset: Changeset, rows: list[_EditRow], child_modes: dict[int, str]
) -> ChangesetOut:
    """Assembles a changeset and its edits."""
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


async def _open_changeset(cern_login: str, session: SessionDep) -> Changeset | None:
    return await session.scalar(
        select(Changeset).where(
            Changeset.created_by == cern_login, Changeset.committed_at.is_(None)
        )
    )


async def _get_or_create_open_changeset(cern_login: str, session: SessionDep) -> Changeset:
    """Returns the caller's open changeset, creating one if absent."""

    changeset = await _open_changeset(cern_login, session)
    if changeset is not None:
        return changeset

    stmt = insert(Changeset).values(created_by=cern_login, comment="")
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[Changeset.created_by], index_where=Changeset.committed_at.is_(None)
    )
    _ = await session.execute(stmt)
    await session.commit()
    changeset = await _open_changeset(cern_login, session)
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


async def _child_modes(rows: list[_EditRow], session: SessionDep) -> dict[int, str]:
    """Mode name for every child key the given edits point at, in one query."""
    key_ids = {
        key_id
        for edit, *_ in rows
        for key_id in cast("dict[str, int | None]", edit.proposed_children or {}).values()
        if key_id is not None
    }
    if not key_ids:
        return {}
    rows_ = await session.execute(
        select(Key.id, Mode.name).join(Mode, Mode.id == Key.mode_id).where(Key.id.in_(key_ids))
    )
    return dict(rows_.tuples().all())


async def _changeset_out(changeset: Changeset, session: SessionDep) -> ChangesetOut:
    rows = await _edit_rows(changeset.id, session)
    return _build_changeset(changeset, rows, await _child_modes(rows, session))


@router.get("/")
async def get_changeset(request: Request, session: SessionDep) -> ChangesetOut | None:
    """Fetches the caller's open changeset and its staged edits, or null if none is open."""
    changeset = await _open_changeset(request.state.claims["cern_upn"], session)
    if changeset is None:
        return None
    return await _changeset_out(changeset, session)


@router.post("/edits")
async def stage_edits(
    edits: list[StagedEditIn], request: Request, session: SessionDep
) -> ChangesetOut:
    """Stages (or re-stages) a set of edits in the caller's open changeset."""
    claims = request.state.claims
    cern_login = claims["cern_upn"]

    await upsert_app_user(claims, session)

    changeset = await _get_or_create_open_changeset(cern_login, session)

    base_keys = [
        await key_or_404(
            edit_in.subsystem_name,
            edit_in.node_name,
            edit_in.mode_name,
            edit_in.base_version,
            session,
        )
        for edit_in in edits
    ]

    # Staged edits are immutable, so re-staging deletes then inserts.
    _ = await session.execute(
        delete(StagedEdit).where(
            StagedEdit.changeset_id == changeset.id,
            StagedEdit.mode_id.in_({key.mode_id for key in base_keys}),
        )
    )

    for edit_in, base_key in zip(edits, base_keys, strict=True):
        session.add(
            StagedEdit(
                changeset_id=changeset.id,
                mode_id=base_key.mode_id,
                base_key_id=base_key.id,
                proposed_payload=edit_in.proposed_payload,
                proposed_children=edit_in.proposed_children,
                comment=edit_in.comment,
                validation_status="skipped",  # hardcoded until we have validation JSON Schemas
            )
        )

    await session.commit()
    return await _changeset_out(changeset, session)


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
