from datetime import UTC, datetime
from typing import NamedTuple, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select, tuple_
from tsgauth.fastapi import JWTBearerClaims

from app.authz import claim_roles, require_writable
from app.config import settings
from app.db.base import SessionDep
from app.db.models import (
    AppUser,
    Changeset,
    Key,
    KeyChild,
    Mode,
    Node,
    NodeEdge,
    Role,
    RoleSubsystem,
    StagedArchival,
    StagedDecommission,
    StagedEdit,
    Subsystem,
)
from app.mail import send_all
from app.notify import (
    Entry,
    archival_entry,
    build_mails,
    bundle_counts,
    decommission_entry,
    edit_entry,
    payload_counts,
)
from app.routers.staging import (
    ChangesetOut,
    changeset_out,
    decommissioned_labels,
    join_mode_names,
    open_changeset,
)

router = APIRouter(
    prefix="/commit",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["commit"],
)


class CommitIn(BaseModel):
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
    mode_archived_at: datetime | None
    node_id: int
    base_version: int | None
    tip_version: int
    category: str | None


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
                validation_status=row.edit.validation_status,
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


def _decommission_keys(
    decommissions: list[StagedDecommission], keys: dict[int, Key], cern_login: str
) -> None:
    for decommission in decommissions:
        key = keys[decommission.key_id]
        key.decommissioned_by = cern_login if decommission.decommissioned else None
        key.decommissioned_at = datetime.now(UTC) if decommission.decommissioned else None


async def _archival_data(
    archivals: list[StagedArchival], session: SessionDep
) -> tuple[dict[int, Mode], dict[int, tuple[str, str, str]]]:
    """Mode entities by mode_id, and mode_id -> (subsystem_name, node_name, mode_name)."""
    if not archivals:
        return {}, {}
    rows = await session.execute(
        select(Mode, Subsystem.name, Node.name)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .where(Mode.id.in_({a.mode_id for a in archivals}))
    )
    modes: dict[int, Mode] = {}
    context: dict[int, tuple[str, str, str]] = {}
    for mode, subsystem_name, node_name in rows:
        modes[mode.id] = mode
        context[mode.id] = (subsystem_name, node_name, mode.name)
    return modes, context


async def _decommission_data(
    decommissions: list[StagedDecommission], session: SessionDep
) -> tuple[dict[int, Key], dict[int, tuple[str, str, str, str]]]:
    """Key entities by key_id, and key_id -> (subsystem_name, node_name, mode_name, label)."""
    if not decommissions:
        return {}, {}
    rows = await session.execute(
        select(Key, Subsystem.name, Node.name, Mode.name)
        .join(Mode, Mode.id == Key.mode_id)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .where(Key.id.in_({d.key_id for d in decommissions}))
    )
    keys: dict[int, Key] = {}
    context: dict[int, tuple[str, str, str, str]] = {}
    for key, subsystem_name, node_name, mode_name in rows:
        keys[key.id] = key
        context[key.id] = (subsystem_name, node_name, mode_name, key.label)
    return keys, context


async def _ancestor_data(
    notifiable_rows: list[_CommitRow], session: SessionDep
) -> tuple[dict[int, str | None], dict[int, dict[str, int]]]:
    """Ancestor key id -> payload, and ancestor key id -> {alias: child_key_id}, for diff counts."""
    ancestor_ids = {
        row.edit.base_key_id or row.edit.copied_from_key_id
        for row in notifiable_rows
        if row.edit.base_key_id or row.edit.copied_from_key_id
    }
    if not ancestor_ids:
        return {}, {}
    payload_rows = await session.execute(
        select(Key.id, Key.payload).where(Key.id.in_(ancestor_ids))
    )
    payloads = dict(payload_rows.tuples().all())
    child_rows = await session.execute(
        select(KeyChild.parent_key_id, KeyChild.alias, KeyChild.child_key_id).where(
            KeyChild.parent_key_id.in_(ancestor_ids)
        )
    )
    children: dict[int, dict[str, int]] = {}
    for parent_key_id, alias, child_key_id in child_rows.tuples():
        children.setdefault(parent_key_id, {})[alias] = child_key_id
    return payloads, children


async def _notification_entries(
    rows: list[_CommitRow],
    keys: list[Key],
    archivals: list[StagedArchival],
    archival_ctx: dict[int, tuple[str, str, str]],
    decommissions: list[StagedDecommission],
    decommission_ctx: dict[int, tuple[str, str, str, str]],
    session: SessionDep,
) -> dict[str, list[Entry]]:
    """Mirrors the sidebar's Version Control panel: same entries, same external-edit filter."""
    notifiable_rows = [row for row in rows if row.category != "external"]
    ancestor_payloads, ancestor_children = await _ancestor_data(notifiable_rows, session)
    keys_by_mode = {key.mode_id: key for key in keys}

    entries: dict[str, list[Entry]] = {}
    for row in notifiable_rows:
        key = keys_by_mode[row.edit.mode_id]
        ancestor_id = row.edit.base_key_id or row.edit.copied_from_key_id
        is_fork = row.base_version is None and row.edit.copied_from_key_id is not None
        if row.edit.proposed_payload is not None:
            counts = payload_counts(ancestor_payloads.get(ancestor_id), row.edit.proposed_payload)
        else:
            proposed_children = cast("dict[str, int | None]", row.edit.proposed_children or {})
            counts = bundle_counts(ancestor_children.get(ancestor_id), proposed_children, key.id)
        entries.setdefault(row.subsystem_name, []).append(
            edit_entry(
                row.subsystem_name,
                row.node_name,
                row.mode_name,
                row.base_version,
                key.version,
                is_fork,
                row.edit.comment,
                counts,
            )
        )

    for archival in archivals:
        sub, node, mode = archival_ctx[archival.mode_id]
        entries.setdefault(sub, []).append(archival_entry(sub, node, mode, archival.archived))

    for decommission in decommissions:
        sub, node, mode, label = decommission_ctx[decommission.key_id]
        entries.setdefault(sub, []).append(
            decommission_entry(sub, node, mode, label, decommission.decommissioned)
        )

    return entries


async def _notification_context(
    subsystems: set[str], session: SessionDep
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Recipient group emails and display name, per subsystem."""
    if not subsystems:
        return {}, {}
    rows = await session.execute(
        select(Subsystem.name, Subsystem.display_name, Role.notification_email)
        .outerjoin(RoleSubsystem, RoleSubsystem.subsystem_id == Subsystem.id)
        .outerjoin(Role, (Role.id == RoleSubsystem.role_id) & Role.notification_email.is_not(None))
        .where(Subsystem.name.in_(subsystems))
    )
    recipients: dict[str, set[str]] = {}
    display_names: dict[str, str] = {}
    for name, display_name, group_email in rows.tuples():
        display_names[name] = display_name or name
        if group_email is not None:
            recipients.setdefault(name, set()).add(group_email)
    return recipients, display_names


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
                Mode.archived_at,
                Node.id,
                Key.version,
                func.coalesce(tip_versions.c.tip_version, 0),
                Node.category,
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
    await require_writable({row.subsystem_name for row in rows}, request.state.claims, session)

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
async def commit_changeset(
    body: CommitIn, request: Request, session: SessionDep, background: BackgroundTasks
) -> None:
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
    decommissions = list(
        await session.scalars(
            select(StagedDecommission).where(StagedDecommission.changeset_id == changeset.id)
        )
    )
    if not rows and not archivals and not decommissions:
        raise HTTPException(status_code=400, detail="changeset has no staged edits")

    archival_modes, archival_ctx = await _archival_data(archivals, session)
    decommission_keys, decommission_ctx = await _decommission_data(decommissions, session)

    archival_subsystems = {sub for sub, _, _ in archival_ctx.values()}
    decommission_subsystems = {sub for sub, _, _, _ in decommission_ctx.values()}
    wanted = {row.subsystem_name for row in rows} | archival_subsystems | decommission_subsystems
    await require_writable(wanted, claims, session)

    if not body.overwrite_conflicts and (conflicts := _conflicts(rows)):
        raise HTTPException(status_code=409, detail=[c.model_dump() for c in conflicts])

    none_aliases, concrete_ids = _proposed_child_refs(rows)

    # Defence in depth: re-check retirement that may have landed between staging and commit.
    base_key_ids = {row.edit.base_key_id for row in rows if row.edit.base_key_id is not None}
    retired_keys = await decommissioned_labels(base_key_ids | concrete_ids, changeset.id, session)
    # Committed state only: an archival by this same changeset isn't applied yet, so it's excluded.
    retired_modes = [
        f"{row.subsystem_name}/{row.node_name}/{row.mode_name}"
        for row in rows
        if row.mode_archived_at is not None
    ]
    if retired_keys or retired_modes:
        parts = []
        if retired_keys:
            parts.append(f"decommissioned key(s): {', '.join(sorted(retired_keys))}")
        if retired_modes:
            parts.append(f"archived mode(s): {', '.join(sorted(retired_modes))}")
        raise HTTPException(status_code=409, detail="; ".join(parts))

    keys = _build_keys(rows, changeset)
    session.add_all(keys)
    await session.flush()

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
        _archive_modes(archivals, archival_modes, cern_login)

    if decommissions:
        _decommission_keys(decommissions, decommission_keys, cern_login)

    changeset.committed_at = datetime.now(UTC)
    changeset.committed_with_roles = claim_roles(claims)

    committed_at = changeset.committed_at

    await session.commit()

    if settings.smtp_host:
        recipients, subsystem_display_names = await _notification_context(wanted, session)
        if recipients:
            entries = await _notification_entries(
                rows, keys, archivals, archival_ctx, decommissions, decommission_ctx, session
            )
            if entries:
                author = await session.get(AppUser, cern_login)
                background.add_task(
                    send_all,
                    build_mails(
                        author.display_name if author else cern_login,
                        cern_login,
                        author.email if author else None,
                        committed_at,
                        entries,
                        recipients,
                        subsystem_display_names,
                    ),
                )
