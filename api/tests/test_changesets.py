import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AppUser, Changeset, StagedEdit
from app.routers.changesets import (
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

    out = _build_changeset(changeset, rows, {9: "special"})

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
        key_id=9, mode_name="special"
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
