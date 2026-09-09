import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AppUser, Changeset, Key, StagedEdit
from app.routers.commit import (
    _build_key_children,
    _build_keys,
    _CommitRow,
    _conflicts,
    _rebased_edits,
)
from app.routers.staging import (
    ProposedChildOut,
    _build_changeset,
    _get_or_create_open_changeset,
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
        validation_status="skipped",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
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
        created_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    rows = [
        (payload_edit, "cms_run", "clock_source", "default", 3, "external"),
        (rebundle_edit, "cms_run", "conf", "default", 1, "algo"),
    ]

    out = _build_changeset(
        changeset, rows, {9: ProposedChildOut(key_id=9, mode_name="special", version=5)}
    )

    assert out.id == 7
    assert out.created_by == "jdoe"
    assert [e.node_name for e in out.edits] == ["clock_source", "conf"]

    external_edit, bundle_edit = out.edits
    assert external_edit.base_version == 3
    assert external_edit.category == "external"
    assert external_edit.proposed_payload == "LHC"
    # Edits and changeset track their own timestamps
    assert external_edit.created_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert bundle_edit.created_at == datetime(2026, 1, 3, tzinfo=UTC)

    assert bundle_edit.base_version == 1
    assert bundle_edit.proposed_children is not None
    assert bundle_edit.proposed_children["clock_source"] is None
    assert bundle_edit.proposed_children["other_child"] == ProposedChildOut(
        key_id=9, mode_name="special", version=5
    )


@pytest.mark.docker
def test_get_or_create_open_changeset_is_race_safe(
    session_factory: async_sessionmaker[AsyncSession],
):
    """Two concurrent requests for the same user's open changeset must not create two rows."""

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


def test_conflicts_ignores_an_old_base_and_flags_a_taken_version():
    """Staging v1 edit while v3 exists is fine; conflicts only once someone else commits v4
    first."""
    promoting_edit = StagedEdit(
        id=1, changeset_id=7, mode_id=118, base_key_id=5, expected_version=4, proposed_payload="x"
    )
    taken_edit = StagedEdit(
        id=2, changeset_id=7, mode_id=119, base_key_id=6, expected_version=2, proposed_payload="y"
    )

    rows = [
        # Based on v1, targeting v4, and the mode is still on v3. Good.
        _CommitRow(promoting_edit, "cms_run", "clock_source", "default", 10, 1, 3),
        # Targeted v2, but the tip has moved to v2 since. Bad.
        _CommitRow(taken_edit, "cms_run", "conf", "default", 11, 1, 2),
    ]

    conflicts = _conflicts(rows)

    assert len(conflicts) == 1
    assert conflicts[0].node_name == "conf"
    assert conflicts[0].base_version == 1
    assert conflicts[0].expected_version == 2
    assert conflicts[0].tip_version == 2


def test_build_keys_lands_on_the_tip_not_the_base():
    """A key promoted from v1 while the mode is on v3 is committed as v4."""
    edit = StagedEdit(
        id=1, changeset_id=7, mode_id=118, base_key_id=5, expected_version=4, proposed_payload="x"
    )
    changeset = Changeset(id=7, created_by="jdoe", comment="")

    rows = [_CommitRow(edit, "cms_run", "clock_source", "default", 10, 1, 3)]

    keys = _build_keys(rows, changeset)

    assert [k.version for k in keys] == [4]
    assert keys[0].label == "cms_run/clock_source/default/v4"
    assert keys[0].mode_id == 118
    assert keys[0].node_id == 10


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
    """Two modes edited on the same node in one changeset must each get their own parent key, not
    whichever one was built last."""
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
