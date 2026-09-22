import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AppUser,
    Changeset,
    Key,
    Mode,
    StagedArchival,
    StagedDecommission,
    StagedEdit,
    Subsystem,
    Vertex,
)
from app.routers.commit import (
    CommitIn,
    _build_key_children,
    _build_keys,
    _CommitRow,
    _conflicts,
    _rebased_edits,
    commit_changeset,
)
from app.routers.staging import (
    ForkIn,
    ProposedChildOut,
    StagedArchivalOut,
    StagedDecommissionOut,
    StagedEditIn,
    _build_changeset,
    _get_or_create_open_changeset,
    _resolve_bases,
    discard_edit,
    fork_mode,
    pending_editors,
    stage_edits,
)
from app.routers.user import upsert_app_user


def _fake_request(cern_login: str) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(claims={"cern_upn": cern_login}))


def test_build_changeset_assembles_edits_and_ripple():
    changeset = Changeset(
        id=7,
        created_by="jdoe",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    payload_edit = StagedEdit(
        id=1,
        changeset_id=7,
        mode_id=118,
        base_key_id=5,
        expected_version=4,
        proposed_payload="LHC",
        proposed_children=None,
        comment="switch clock source",
        validation_status="failed",
    )
    rebundle_edit = StagedEdit(
        id=2,
        changeset_id=7,
        mode_id=119,
        base_key_id=6,
        expected_version=2,
        proposed_payload=None,
        proposed_children={"clock_source": None, "other_child": 9},
        comment="point at the new clock source",
        validation_status="skipped",
    )

    rows = [
        (payload_edit, "cms_run", "clock_source", "default", 3, "external"),
        (rebundle_edit, "cms_run", "conf", "default", 1, "algo"),
    ]

    archival = StagedArchival(changeset_id=7, mode_id=120, archived=True)
    archival_rows = [(archival, "cms_run", "conf", "retired")]

    decommission = StagedDecommission(changeset_id=7, key_id=42, decommissioned=True)
    decommission_rows = [(decommission, "cms_run", "conf", "default", 3, "cms_run/conf/default/v3")]

    out = _build_changeset(
        changeset,
        rows,
        {
            9: ProposedChildOut(
                key_id=9, mode_name="special", version=5, label="cms_run/conf/special/v5"
            )
        },
        archival_rows,
        decommission_rows,
    )

    assert out.id == 7
    assert out.created_by == "jdoe"
    assert [e.vertex_name for e in out.edits] == ["clock_source", "conf"]

    assert out.archivals == [
        StagedArchivalOut(
            mode_id=120,
            subsystem_name="cms_run",
            vertex_name="conf",
            mode_name="retired",
            archived=True,
        )
    ]

    assert out.decommissions == [
        StagedDecommissionOut(
            key_id=42,
            subsystem_name="cms_run",
            vertex_name="conf",
            mode_name="default",
            version=3,
            label="cms_run/conf/default/v3",
            decommissioned=True,
        )
    ]

    external_edit, bundle_edit = out.edits
    assert external_edit.base_version == 3
    assert external_edit.category == "external"
    assert external_edit.proposed_payload == "LHC"
    assert external_edit.validation_status == "failed"

    assert bundle_edit.base_version == 1
    assert bundle_edit.proposed_children is not None
    assert bundle_edit.proposed_children["clock_source"] is None
    assert bundle_edit.proposed_children["other_child"] == ProposedChildOut(
        key_id=9, mode_name="special", version=5, label="cms_run/conf/special/v5"
    )


def test_build_changeset_handles_a_fork_with_no_base_key():
    """base_version is None when there's no base key."""
    changeset = Changeset(id=7, created_by="jdoe", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    fork_edit = StagedEdit(
        id=1,
        changeset_id=7,
        mode_id=118,
        base_key_id=None,
        expected_version=1,
        proposed_payload="LHC",
        proposed_children=None,
        comment="fork",
        validation_status="skipped",
    )

    rows = [(fork_edit, "cms_run", "clock_source", "collisions2026", None, "external")]

    out = _build_changeset(changeset, rows, {}, [], [])

    assert out.edits[0].base_version is None
    assert out.edits[0].expected_version == 1


def test_build_changeset_reports_the_fork_source():
    changeset = Changeset(id=7, created_by="jdoe", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    fork_edit = StagedEdit(
        id=1,
        changeset_id=7,
        mode_id=118,
        base_key_id=None,
        copied_from_key_id=42,
        expected_version=1,
        proposed_payload="LHC",
        proposed_children=None,
        comment="fork",
        validation_status="skipped",
    )

    rows = [(fork_edit, "cms_run", "clock_source", "collisions2026", None, "external")]
    out = _build_changeset(
        changeset,
        rows,
        {
            42: ProposedChildOut(
                key_id=42, mode_name="default", version=3, label="cms_run/clock_source/default/v3"
            )
        },
        [],
        [],
    )

    assert out.edits[0].copied_from == ProposedChildOut(
        key_id=42, mode_name="default", version=3, label="cms_run/clock_source/default/v3"
    )


def _fresh_mode_row() -> _CommitRow:
    """tip_version 0, no base key; commits as v1."""
    edit = StagedEdit(
        id=1,
        changeset_id=7,
        mode_id=118,
        base_key_id=None,
        expected_version=1,
        proposed_payload="x",
    )
    return _CommitRow(edit, "cms_run", "clock_source", "collisions2026", None, 10, None, 0, "algo")


def test_build_keys_lands_on_v1_for_a_fresh_mode():
    changeset = Changeset(id=7, created_by="jdoe")

    keys = _build_keys([_fresh_mode_row()], changeset)

    assert [k.version for k in keys] == [1]
    assert keys[0].label == "cms_run/clock_source/collisions2026/v1"


def test_conflicts_is_empty_for_a_fresh_mode():
    """v1 vs tip 0 isn't a conflict, it's the first key."""
    assert _conflicts([_fresh_mode_row()]) == []


@pytest.mark.docker
def test_get_or_create_open_changeset_is_race_safe(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> tuple[int, int, list[int]]:
        async with session_factory() as setup:
            setup.add(AppUser(cern_login="racer", display_name="Racer"))
            await setup.commit()

        async with session_factory() as session_a, session_factory() as session_b:
            changeset_a, changeset_b = await asyncio.gather(
                _get_or_create_open_changeset("racer", session_a),
                _get_or_create_open_changeset("racer", session_b),
            )

        async with session_factory() as session:
            open_ids = (
                await session.scalars(
                    select(Changeset.id).where(
                        Changeset.created_by == "racer", Changeset.committed_at.is_(None)
                    )
                )
            ).all()
        return changeset_a.id, changeset_b.id, list(open_ids)

    id_a, id_b, open_ids = asyncio.run(run())
    assert id_a == id_b
    assert open_ids == [id_a]


async def _forked_mode(
    session_factory: async_sessionmaker[AsyncSession], *, cern_login: str, mode_name: str
) -> tuple[int, int]:
    """Fresh fork, no key yet, staged as v1 on the seeded cms_run/clock_source vertex."""
    async with session_factory() as session:
        session.add(AppUser(cern_login=cern_login, display_name=cern_login))
        vertex_id = await session.scalar(
            select(Vertex.id)
            .join(Subsystem, Subsystem.id == Vertex.subsystem_id)
            .where(Subsystem.name == "cms_run", Vertex.name == "clock_source")
        )
        assert vertex_id is not None
        mode = Mode(vertex_id=vertex_id, name=mode_name, description="d", created_by=cern_login)
        session.add(mode)
        changeset = Changeset(created_by=cern_login)
        session.add(changeset)
        await session.flush()
        session.add(
            StagedEdit(
                changeset_id=changeset.id,
                mode_id=mode.id,
                base_key_id=None,
                expected_version=1,
                proposed_payload="LHC",
                comment="fork",
                validation_status="skipped",
            )
        )
        await session.commit()
        return changeset.id, mode.id


@pytest.mark.docker
def test_discard_edit_removes_only_that_edit_and_its_orphan_fork(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> tuple[bool, bool, bool]:
        changeset_id, forked_mode_id = await _forked_mode(
            session_factory, cern_login="discarder", mode_name="fork_to_discard"
        )
        async with session_factory() as session:
            edit_id = await session.scalar(
                select(StagedEdit.id).where(StagedEdit.mode_id == forked_mode_id)
            )
            assert edit_id is not None

            vertex_id = await session.scalar(
                select(Vertex.id)
                .join(Subsystem, Subsystem.id == Vertex.subsystem_id)
                .where(Subsystem.name == "cms_run", Vertex.name == "clock_source")
            )
            other_mode = Mode(
                vertex_id=vertex_id, name="fork_to_keep", description="d", created_by="discarder"
            )
            session.add(other_mode)
            await session.flush()
            session.add(
                StagedEdit(
                    changeset_id=changeset_id,
                    mode_id=other_mode.id,
                    base_key_id=None,
                    expected_version=1,
                    proposed_payload="LHC",
                    comment="fork",
                    validation_status="skipped",
                )
            )
            await session.commit()
            other_mode_id = other_mode.id

        request = _fake_request("discarder")
        async with session_factory() as session:
            await discard_edit(edit_id, request, session)

        async with session_factory() as session:
            discarded_edit_gone = (await session.get(StagedEdit, edit_id)) is None
            forked_mode_gone = (await session.get(Mode, forked_mode_id)) is None
            other_edit_remains = (
                await session.scalar(
                    select(StagedEdit.id).where(StagedEdit.mode_id == other_mode_id)
                )
            ) is not None

        return discarded_edit_gone, forked_mode_gone, other_edit_remains

    discarded_edit_gone, forked_mode_gone, other_edit_remains = asyncio.run(run())
    assert discarded_edit_gone
    assert forked_mode_gone
    assert other_edit_remains


@pytest.mark.docker
def test_resolve_bases_restages_onto_a_forked_modes_own_edit(
    session_factory: async_sessionmaker[AsyncSession],
):
    """Fork's v1 has no key for keys_by_locator; must match its own staged edit, not 404."""
    changeset_id, mode_id = asyncio.run(
        _forked_mode(session_factory, cern_login="forker", mode_name="collisions2026")
    )

    async def run():
        async with session_factory() as session:
            return await _resolve_bases(
                [
                    StagedEditIn(
                        subsystem_name="cms_run",
                        vertex_name="clock_source",
                        mode_name="collisions2026",
                        base_version=1,
                        proposed_payload="new payload",
                        comment="edit",
                    )
                ],
                changeset_id,
                session,
            )

    [base] = asyncio.run(run())
    assert base.mode_id == mode_id
    assert base.base_key_id is None
    assert base.expected_version == 1
    assert base.copied_from_key_id is None


@pytest.mark.docker
def test_restaging_a_fresh_fork_back_to_its_source_leaves_nothing_pending(
    session_factory: async_sessionmaker[AsyncSession],
):
    """A freshly-forked mode has no base_key_id yet, only copied_from_key_id; the no-op
    suppression must compare against that too, not just an already-committed mode's base_key_id."""
    cern_login = "fork_noop"
    request = SimpleNamespace(
        state=SimpleNamespace(
            claims={
                "cern_upn": cern_login,
                "name": cern_login,
                "resource_access": {"keytree": {"roles": ["keytree_superuser"]}},
            }
        )
    )

    async def run() -> int | None:
        async with session_factory() as session:
            await upsert_app_user({"cern_upn": cern_login, "name": cern_login}, session)
            vertex_id = await session.scalar(
                select(Vertex.id)
                .join(Subsystem, Subsystem.id == Vertex.subsystem_id)
                .where(Subsystem.name == "cms_run", Vertex.name == "clock_source")
            )
            assert vertex_id is not None
            source_mode = Mode(
                vertex_id=vertex_id,
                name="fork_noop_source",
                description="d",
                created_by=cern_login,
            )
            session.add(source_mode)
            changeset = Changeset(created_by=cern_login)
            session.add(changeset)
            await session.flush()
            session.add(
                StagedEdit(
                    changeset_id=changeset.id,
                    mode_id=source_mode.id,
                    base_key_id=None,
                    expected_version=1,
                    proposed_payload="original content",
                    comment="seed",
                    validation_status="skipped",
                )
            )
            await session.commit()

        async with session_factory() as session:
            await commit_changeset(CommitIn(), request, session, BackgroundTasks())

        async with session_factory() as session:
            await fork_mode(
                ForkIn(
                    subsystem_name="cms_run",
                    vertex_name="clock_source",
                    mode_name="fork_noop_source",
                    base_version=1,
                    proposed_payload="original content",
                    comment="fork",
                    new_mode_name="fork_noop_target",
                    description="fork",
                ),
                request,
                session,
            )

        # Re-stage the freshly-forked mode back to the exact content it was copied from.
        async with session_factory() as session:
            await stage_edits(
                [
                    StagedEditIn(
                        subsystem_name="cms_run",
                        vertex_name="clock_source",
                        mode_name="fork_noop_target",
                        base_version=1,
                        proposed_payload="original content",
                        comment="revert",
                    )
                ],
                request,
                session,
            )

        async with session_factory() as session:
            target_mode_id = await session.scalar(
                select(Mode.id).where(Mode.vertex_id == vertex_id, Mode.name == "fork_noop_target")
            )
            return await session.scalar(
                select(StagedEdit.id).where(StagedEdit.mode_id == target_mode_id)
            )

    remaining_edit_id = asyncio.run(run())
    assert remaining_edit_id is None


@pytest.mark.docker
def test_pending_editors_excludes_self_and_committed_changesets(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> tuple[list, list, list]:
        changeset_id, mode_id = await _forked_mode(
            session_factory, cern_login="editor_a", mode_name="pending_editors_test"
        )
        async with session_factory() as session:
            user = await session.get(AppUser, "editor_a")
            assert user is not None
            user.email = "editor_a@cern.ch"
            await session.commit()

        async with session_factory() as session:
            seen_by_other = await pending_editors(mode_id, _fake_request("editor_b"), session)
        async with session_factory() as session:
            seen_by_self = await pending_editors(mode_id, _fake_request("editor_a"), session)

        async with session_factory() as session:
            changeset = await session.get(Changeset, changeset_id)
            assert changeset is not None
            changeset.committed_at = datetime(2026, 1, 1, tzinfo=UTC)
            changeset.committed_with_roles = []
            await session.commit()
        async with session_factory() as session:
            seen_after_commit = await pending_editors(mode_id, _fake_request("editor_b"), session)

        return seen_by_other, seen_by_self, seen_after_commit

    seen_by_other, seen_by_self, seen_after_commit = asyncio.run(run())
    assert [e.cern_login for e in seen_by_other] == ["editor_a"]
    assert seen_by_other[0].display_name == "editor_a"
    assert seen_by_other[0].email == "editor_a@cern.ch"
    assert seen_by_self == []
    assert seen_after_commit == []


def test_conflicts_ignores_an_old_base_and_flags_a_taken_version():
    """v1 staged while v3 exists is fine; conflict only once v4 is committed."""
    promoting_edit = StagedEdit(
        id=1, changeset_id=7, mode_id=118, base_key_id=5, expected_version=4, proposed_payload="x"
    )
    taken_edit = StagedEdit(
        id=2, changeset_id=7, mode_id=119, base_key_id=6, expected_version=2, proposed_payload="y"
    )

    rows = [
        # base v1, targets v4, mode still on v3: fine
        _CommitRow(promoting_edit, "cms_run", "clock_source", "default", None, 10, 1, 3, "algo"),
        # targeted v2, tip moved to v2 since: conflict
        _CommitRow(taken_edit, "cms_run", "conf", "default", None, 11, 1, 2, "algo"),
    ]

    conflicts = _conflicts(rows)

    assert len(conflicts) == 1
    assert conflicts[0].vertex_name == "conf"
    assert conflicts[0].base_version == 1
    assert conflicts[0].expected_version == 2
    assert conflicts[0].tip_version == 2


def test_build_keys_lands_on_the_tip_not_the_base():
    """v1 edit promoted while the mode's on v3 commits as v4."""
    edit = StagedEdit(
        id=1,
        changeset_id=7,
        mode_id=118,
        base_key_id=5,
        expected_version=4,
        proposed_payload="x",
        validation_status="passed",
    )
    changeset = Changeset(id=7, created_by="jdoe")

    rows = [_CommitRow(edit, "cms_run", "clock_source", "default", None, 10, 1, 3, "algo")]

    keys = _build_keys(rows, changeset)

    assert [k.version for k in keys] == [4]
    assert keys[0].label == "cms_run/clock_source/default/v4"
    assert keys[0].mode_id == 118
    assert keys[0].vertex_id == 10
    assert keys[0].validation_status == "passed"


def test_rebased_edits_move_the_base_and_keep_the_proposal():
    edit = StagedEdit(
        id=2,
        changeset_id=7,
        mode_id=119,
        base_key_id=6,
        expected_version=2,
        proposed_payload="y",
        proposed_children={"clock": 9},
        comment="point at the new clock",
        validation_status="skipped",
    )

    rebased = _rebased_edits(
        [_CommitRow(edit, "cms_run", "conf", "default", None, 11, 1, 2, None)],
        tip_keys={119: (60, 2)},
    )

    assert len(rebased) == 1
    # Rebased onto the key committed since, so the next commit lands on v3
    assert rebased[0].base_key_id == 60
    assert rebased[0].expected_version == 3
    # The staged proposal survives untouched
    assert rebased[0].proposed_payload == "y"
    assert rebased[0].proposed_children == {"clock": 9}
    assert rebased[0].comment == "point at the new clock"


def test_build_key_children_resolves_none_to_same_changeset_key():
    parent_key = Key(id=100, mode_id=1, vertex_id=11, version=2, label="cms_run/conf/default/v2")
    child_key = Key(id=101, mode_id=2, vertex_id=20, version=1, label="cms_run/clock/default/v1")

    edit = StagedEdit(
        id=1,
        changeset_id=7,
        mode_id=1,
        base_key_id=5,
        proposed_children={"clock_source": None, "other_child": 9},
    )
    rows = [_CommitRow(edit, "cms_run", "conf", "default", None, 11, 1, 1, None)]

    children = _build_key_children(
        rows,
        keys=[parent_key, child_key],
        child_vertex_of={(11, "clock_source"): 20},
        vertex_of_key={9: 30},
    )

    by_alias = {c.alias: c for c in children}
    assert by_alias["clock_source"].child_key_id == 101
    assert by_alias["clock_source"].child_vertex_id == 20
    assert by_alias["other_child"].child_key_id == 9
    assert by_alias["other_child"].child_vertex_id == 30
    assert all(c.parent_key_id == 100 and c.parent_vertex_id == 11 for c in children)


def test_build_key_children_raises_when_none_has_no_target():
    parent_key = Key(id=100, mode_id=1, vertex_id=11, version=2, label="cms_run/conf/default/v2")
    edit = StagedEdit(
        id=1, changeset_id=7, mode_id=1, base_key_id=5, proposed_children={"clock_source": None}
    )
    rows = [_CommitRow(edit, "cms_run", "conf", "default", None, 11, 1, 1, None)]

    with pytest.raises(HTTPException) as exc_info:
        _ = _build_key_children(
            rows,
            keys=[parent_key],
            child_vertex_of={},
            vertex_of_key={},
        )

    assert exc_info.value.status_code == 400


def test_build_key_children_keys_parent_by_mode_not_vertex():
    """Same vertex, two modes edited: each gets its own parent key, not whichever built last."""
    default_key = Key(id=100, mode_id=1, vertex_id=11, version=2, label="cms_run/conf/default/v2")
    algo_key = Key(id=200, mode_id=2, vertex_id=11, version=4, label="cms_run/conf/algo/v4")

    default_edit = StagedEdit(
        id=1, changeset_id=7, mode_id=1, base_key_id=5, proposed_children={"a": 9}
    )
    algo_edit = StagedEdit(
        id=2, changeset_id=7, mode_id=2, base_key_id=6, proposed_children={"b": 9}
    )
    rows = [
        _CommitRow(default_edit, "cms_run", "conf", "default", None, 11, 1, 1, None),
        _CommitRow(algo_edit, "cms_run", "conf", "algo", None, 11, 3, 3, None),
    ]

    children = _build_key_children(
        rows,
        keys=[default_key, algo_key],
        child_vertex_of={},
        vertex_of_key={9: 30},
    )

    by_alias = {c.alias: c for c in children}
    assert by_alias["a"].parent_key_id == 100
    assert by_alias["b"].parent_key_id == 200


def test_build_key_children_raises_on_unknown_concrete_key_id():
    parent_key = Key(id=100, mode_id=1, vertex_id=11, version=2, label="cms_run/conf/default/v2")
    edit = StagedEdit(
        id=1, changeset_id=7, mode_id=1, base_key_id=5, proposed_children={"clock_source": 999}
    )
    rows = [_CommitRow(edit, "cms_run", "conf", "default", None, 11, 1, 1, None)]

    with pytest.raises(HTTPException) as exc_info:
        _ = _build_key_children(
            rows,
            keys=[parent_key],
            child_vertex_of={},
            vertex_of_key={},
        )

    assert exc_info.value.status_code == 400
