import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AppUser, Changeset, Key, Mode, Node, StagedArchival, StagedEdit, Subsystem
from app.routers.commit import (
    _build_key_children,
    _build_keys,
    _CommitRow,
    _conflicts,
    _rebased_edits,
)
from app.routers.staging import (
    ProposedChildOut,
    StagedArchivalOut,
    StagedEditIn,
    _build_changeset,
    _get_or_create_open_changeset,
    _resolve_bases,
)


def test_build_changeset_assembles_edits_and_ripple():
    changeset = Changeset(
        id=7,
        created_by="jdoe",
        comment="",
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

    out = _build_changeset(
        changeset,
        rows,
        {
            9: ProposedChildOut(
                key_id=9, mode_name="special", version=5, label="cms_run/conf/special/v5"
            )
        },
        archival_rows,
    )

    assert out.id == 7
    assert out.created_by == "jdoe"
    assert [e.node_name for e in out.edits] == ["clock_source", "conf"]

    assert out.archivals == [
        StagedArchivalOut(
            mode_id=120,
            subsystem_name="cms_run",
            node_name="conf",
            mode_name="retired",
            archived=True,
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
    changeset = Changeset(
        id=7, created_by="jdoe", comment="", created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
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

    out = _build_changeset(changeset, rows, {}, [])

    assert out.edits[0].base_version is None
    assert out.edits[0].expected_version == 1


def test_build_changeset_reports_the_fork_source():
    changeset = Changeset(
        id=7, created_by="jdoe", comment="", created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
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
    return _CommitRow(edit, "cms_run", "clock_source", "collisions2026", 10, None, 0)


def test_build_keys_lands_on_v1_for_a_fresh_mode():
    changeset = Changeset(id=7, created_by="jdoe", comment="")

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
    """Fresh fork, no key yet, staged as v1 on the seeded cms_run/clock_source node."""
    async with session_factory() as session:
        session.add(AppUser(cern_login=cern_login, display_name=cern_login))
        node_id = await session.scalar(
            select(Node.id)
            .join(Subsystem, Subsystem.id == Node.subsystem_id)
            .where(Subsystem.name == "cms_run", Node.name == "clock_source")
        )
        assert node_id is not None
        mode = Mode(node_id=node_id, name=mode_name, description="d", created_by=cern_login)
        session.add(mode)
        changeset = Changeset(created_by=cern_login, comment="")
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
                        node_name="clock_source",
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
        _CommitRow(promoting_edit, "cms_run", "clock_source", "default", 10, 1, 3),
        # targeted v2, tip moved to v2 since: conflict
        _CommitRow(taken_edit, "cms_run", "conf", "default", 11, 1, 2),
    ]

    conflicts = _conflicts(rows)

    assert len(conflicts) == 1
    assert conflicts[0].node_name == "conf"
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
    changeset = Changeset(id=7, created_by="jdoe", comment="")

    rows = [_CommitRow(edit, "cms_run", "clock_source", "default", 10, 1, 3)]

    keys = _build_keys(rows, changeset)

    assert [k.version for k in keys] == [4]
    assert keys[0].label == "cms_run/clock_source/default/v4"
    assert keys[0].mode_id == 118
    assert keys[0].node_id == 10
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
        [_CommitRow(edit, "cms_run", "conf", "default", 11, 1, 2)], tip_keys={119: (60, 2)}
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
    parent_key = Key(id=100, mode_id=1, node_id=11, version=2, label="cms_run/conf/default/v2")
    child_key = Key(id=101, mode_id=2, node_id=20, version=1, label="cms_run/clock/default/v1")

    edit = StagedEdit(
        id=1,
        changeset_id=7,
        mode_id=1,
        base_key_id=5,
        proposed_children={"clock_source": None, "other_child": 9},
    )
    rows = [_CommitRow(edit, "cms_run", "conf", "default", 11, 1, 1)]

    children = _build_key_children(
        rows,
        keys=[parent_key, child_key],
        child_node_of={(11, "clock_source"): 20},
        node_of_key={9: 30},
    )

    by_alias = {c.alias: c for c in children}
    assert by_alias["clock_source"].child_key_id == 101
    assert by_alias["clock_source"].child_node_id == 20
    assert by_alias["other_child"].child_key_id == 9
    assert by_alias["other_child"].child_node_id == 30
    assert all(c.parent_key_id == 100 and c.parent_node_id == 11 for c in children)


def test_build_key_children_raises_when_none_has_no_target():
    parent_key = Key(id=100, mode_id=1, node_id=11, version=2, label="cms_run/conf/default/v2")
    edit = StagedEdit(
        id=1, changeset_id=7, mode_id=1, base_key_id=5, proposed_children={"clock_source": None}
    )
    rows = [_CommitRow(edit, "cms_run", "conf", "default", 11, 1, 1)]

    with pytest.raises(HTTPException) as exc_info:
        _ = _build_key_children(
            rows,
            keys=[parent_key],
            child_node_of={},
            node_of_key={},
        )

    assert exc_info.value.status_code == 400


def test_build_key_children_keys_parent_by_mode_not_node():
    """Same node, two modes edited: each gets its own parent key, not whichever built last."""
    default_key = Key(id=100, mode_id=1, node_id=11, version=2, label="cms_run/conf/default/v2")
    algo_key = Key(id=200, mode_id=2, node_id=11, version=4, label="cms_run/conf/algo/v4")

    default_edit = StagedEdit(
        id=1, changeset_id=7, mode_id=1, base_key_id=5, proposed_children={"a": 9}
    )
    algo_edit = StagedEdit(
        id=2, changeset_id=7, mode_id=2, base_key_id=6, proposed_children={"b": 9}
    )
    rows = [
        _CommitRow(default_edit, "cms_run", "conf", "default", 11, 1, 1),
        _CommitRow(algo_edit, "cms_run", "conf", "algo", 11, 3, 3),
    ]

    children = _build_key_children(
        rows,
        keys=[default_key, algo_key],
        child_node_of={},
        node_of_key={9: 30},
    )

    by_alias = {c.alias: c for c in children}
    assert by_alias["a"].parent_key_id == 100
    assert by_alias["b"].parent_key_id == 200


def test_build_key_children_raises_on_unknown_concrete_key_id():
    parent_key = Key(id=100, mode_id=1, node_id=11, version=2, label="cms_run/conf/default/v2")
    edit = StagedEdit(
        id=1, changeset_id=7, mode_id=1, base_key_id=5, proposed_children={"clock_source": 999}
    )
    rows = [_CommitRow(edit, "cms_run", "conf", "default", 11, 1, 1)]

    with pytest.raises(HTTPException) as exc_info:
        _ = _build_key_children(
            rows,
            keys=[parent_key],
            child_node_of={},
            node_of_key={},
        )

    assert exc_info.value.status_code == 400
