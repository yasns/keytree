import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    Changeset,
    Key,
    Mode,
    Node,
    StagedDecommission,
    StagedEdit,
    Subsystem,
)
from app.routers.commit import CommitIn, commit_changeset
from app.routers.keys import (
    RetiredRefOut,
    _build_child_meta,
    _build_key_detail,
    _retired_descendants,
    search_keys,
)
from app.routers.staging import (
    ArchivalIn,
    DecommissionIn,
    StagedEditIn,
    discard_changeset,
    stage_edits,
    toggle_archival,
    toggle_decommission,
)
from app.routers.user import upsert_app_user


def _key() -> Key:
    return Key(
        id=9,
        mode_id=3,
        node_id=42,
        version=2,
        label="ugt/l1_menu/default/v2",
        payload="menu contents",
        staged_edit_id=1,
        created_by="jdoe",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        comment="new menu",
        validation_status="skipped",
    )


def test_build_child_meta_fills_key_fields():
    meta = _build_child_meta(("l1_menu", _key(), 42, "l1_menu", "ugt", "menu", "default"))

    assert meta.id == 9
    assert meta.label == "ugt/l1_menu/default/v2"
    assert meta.mode_name == "default"
    assert meta.version == 2
    assert meta.created_by == "jdoe"
    # Payload is only carried for external children
    assert meta.payload is None


def test_build_child_meta_carries_external_payload():
    meta = _build_child_meta(("clock", _key(), 7, "clock_source", "cms_run", "external", "default"))

    assert meta.payload == "menu contents"


def test_build_child_meta_lists_empty_alias_with_null_key():
    meta = _build_child_meta(("l1_menu", None, 42, "l1_menu", "ugt", "menu", None))

    assert meta.alias == "l1_menu"
    # structural fields come off the edge: row still renders/refills
    assert meta.node_id == 42
    assert meta.node_name == "l1_menu"
    assert meta.subsystem_name == "ugt"
    assert meta.category == "menu"
    # Everything off the child key is absent
    assert meta.id is None
    assert meta.label is None
    assert meta.mode_name is None
    assert meta.version is None
    assert meta.created_by is None
    assert meta.created_at is None
    assert meta.comment is None
    assert meta.payload is None


def test_build_key_detail_fills_display_name_and_ancestor():
    out = _build_key_detail(_key(), "Jane Doe", "default", 3, "ugt/l1_menu/default/v3", None, [])

    assert out.created_by_display_name == "Jane Doe"
    assert out.based_on is not None
    assert out.based_on.mode_name == "default"
    assert out.based_on.version == 3
    assert out.based_on.label == "ugt/l1_menu/default/v3"


def test_build_key_detail_has_no_ancestor_without_fork_source_or_prior_version():
    out = _build_key_detail(_key(), "Jane Doe", None, None, None, None, [])

    assert out.based_on is None


def test_build_key_detail_carries_decommission_and_retired_descendants():
    key = _key()
    key.decommissioned_by = "jdoe"
    key.decommissioned_at = datetime(2026, 2, 1, tzinfo=UTC)
    out = _build_key_detail(
        key,
        "Jane Doe",
        None,
        None,
        None,
        "Jane Doe",
        [RetiredRefOut(label="ugt/l1_menu/other/v1", reason="mode_archived")],
    )

    assert out.decommissioned_by == "jdoe"
    assert out.decommissioned_by_display_name == "Jane Doe"
    assert out.retired_descendants == [
        RetiredRefOut(label="ugt/l1_menu/other/v1", reason="mode_archived")
    ]


def _fake_request(cern_login: str) -> SimpleNamespace:
    claims = {
        "cern_upn": cern_login,
        "name": cern_login,
        "resource_access": {"keytree": {"roles": ["keytree_superuser"]}},
    }
    return SimpleNamespace(state=SimpleNamespace(claims=claims))


async def _forked_key(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    cern_login: str,
    subsystem: str,
    node: str,
    mode_name: str,
    payload: str,
) -> None:
    """Fresh mode on a seeded node, committed straight to v1 with `payload`."""
    async with session_factory() as session:
        await upsert_app_user({"cern_upn": cern_login, "name": cern_login}, session)
        node_id = await session.scalar(
            select(Node.id)
            .join(Subsystem, Subsystem.id == Node.subsystem_id)
            .where(Subsystem.name == subsystem, Node.name == node)
        )
        assert node_id is not None
        mode = Mode(node_id=node_id, name=mode_name, description="d", created_by=cern_login)
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
                proposed_payload=payload,
                comment="seed",
                validation_status="skipped",
            )
        )
        await session.commit()
    async with session_factory() as session:
        await commit_changeset(CommitIn(), _fake_request(cern_login), session, BackgroundTasks())


async def _restage_key(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    cern_login: str,
    subsystem: str,
    node: str,
    mode_name: str,
    base_version: int,
    payload: str,
) -> None:
    """Commits a new version on top of an already-committed mode."""
    request = _fake_request(cern_login)
    async with session_factory() as session:
        await stage_edits(
            [
                StagedEditIn(
                    subsystem_name=subsystem,
                    node_name=node,
                    mode_name=mode_name,
                    base_version=base_version,
                    proposed_payload=payload,
                    comment="restage",
                )
            ],
            request,
            session,
        )
    async with session_factory() as session:
        await commit_changeset(CommitIn(), request, session, BackgroundTasks())


async def _key_id_by_label(session_factory: async_sessionmaker[AsyncSession], label: str) -> int:
    async with session_factory() as session:
        key_id = await session.scalar(select(Key.id).where(Key.label == label))
        assert key_id is not None
        return key_id


async def _mode_id(
    session_factory: async_sessionmaker[AsyncSession], subsystem: str, node: str, mode_name: str
) -> int:
    async with session_factory() as session:
        mode_id = await session.scalar(
            select(Mode.id)
            .join(Node, Node.id == Mode.node_id)
            .join(Subsystem, Subsystem.id == Node.subsystem_id)
            .where(Subsystem.name == subsystem, Node.name == node, Mode.name == mode_name)
        )
        assert mode_id is not None
        return mode_id


@pytest.mark.docker
def test_toggle_decommission_stages_then_cancels_on_a_second_click(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> tuple[bool | None, list]:
        await _forked_key(
            session_factory,
            cern_login="decommission_toggle",
            subsystem="ugt",
            node="l1_menu",
            mode_name="decommission_toggle_mode",
            payload="<menu/>",
        )
        key_id = await _key_id_by_label(session_factory, "ugt/l1_menu/decommission_toggle_mode/v1")
        request = _fake_request("decommission_toggle")

        async with session_factory() as session:
            staged = await toggle_decommission(DecommissionIn(key_id=key_id), request, session)
        first_pass = staged.decommissions[0].decommissioned if staged.decommissions else None

        async with session_factory() as session:
            cancelled = await toggle_decommission(DecommissionIn(key_id=key_id), request, session)

        return first_pass, cancelled.decommissions

    first_pass, decommissions_after_cancel = asyncio.run(run())
    assert first_pass is True
    assert decommissions_after_cancel == []


@pytest.mark.docker
def test_committing_a_staged_decommission_updates_the_key(
    session_factory: async_sessionmaker[AsyncSession],
):
    """decommissioned_by/decommissioned_at clear together on recommission."""

    async def run() -> tuple[str | None, object, str | None, object]:
        await _forked_key(
            session_factory,
            cern_login="decommission_commit",
            subsystem="ugt",
            node="l1_menu",
            mode_name="decommission_commit_mode",
            payload="<menu/>",
        )
        key_id = await _key_id_by_label(session_factory, "ugt/l1_menu/decommission_commit_mode/v1")
        request = _fake_request("decommission_commit")

        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=key_id), request, session)
        async with session_factory() as session:
            await commit_changeset(CommitIn(), request, session, BackgroundTasks())
        async with session_factory() as session:
            decommissioned = await session.get(Key, key_id)
            assert decommissioned is not None
            after_decommission = (
                decommissioned.decommissioned_by,
                decommissioned.decommissioned_at,
            )

        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=key_id), request, session)
        async with session_factory() as session:
            await commit_changeset(CommitIn(), request, session, BackgroundTasks())
        async with session_factory() as session:
            recommissioned = await session.get(Key, key_id)
            assert recommissioned is not None
            after_recommission = (
                recommissioned.decommissioned_by,
                recommissioned.decommissioned_at,
            )

        return (*after_decommission, *after_recommission)

    decommissioned_by, decommissioned_at, recommissioned_by, recommissioned_at = asyncio.run(run())
    assert decommissioned_by == "decommission_commit"
    assert decommissioned_at is not None
    assert recommissioned_by is None
    assert recommissioned_at is None


@pytest.mark.docker
def test_discarding_an_open_changeset_clears_its_staged_decommission(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> int:
        await _forked_key(
            session_factory,
            cern_login="decommission_discard",
            subsystem="ugt",
            node="l1_menu",
            mode_name="decommission_discard_mode",
            payload="<menu/>",
        )
        key_id = await _key_id_by_label(session_factory, "ugt/l1_menu/decommission_discard_mode/v1")
        request = _fake_request("decommission_discard")

        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=key_id), request, session)
        async with session_factory() as session:
            await discard_changeset(request, session)
        async with session_factory() as session:
            remaining = (
                await session.scalars(
                    select(StagedDecommission).where(StagedDecommission.key_id == key_id)
                )
            ).all()
            return len(remaining)

    assert asyncio.run(run()) == 0


@pytest.mark.docker
def test_staging_rejects_decommissioned_base_and_child_keys(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> tuple[int | None, int | None]:
        # Distinct logins: a rejected stage_edits leaves an empty changeset that would collide.
        base_login = "decommission_guard_base"
        base_request = _fake_request(base_login)

        await _forked_key(
            session_factory,
            cern_login=base_login,
            subsystem="ugt",
            node="l1_menu",
            mode_name="guard_base_mode",
            payload="<menu/>",
        )
        base_key_id = await _key_id_by_label(session_factory, "ugt/l1_menu/guard_base_mode/v1")
        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=base_key_id), base_request, session)
        async with session_factory() as session:
            await commit_changeset(CommitIn(), base_request, session, BackgroundTasks())

        base_status: int | None = None
        try:
            async with session_factory() as session:
                await stage_edits(
                    [
                        StagedEditIn(
                            subsystem_name="ugt",
                            node_name="l1_menu",
                            mode_name="guard_base_mode",
                            base_version=1,
                            proposed_payload="attempted v2",
                            comment="should be rejected",
                        )
                    ],
                    base_request,
                    session,
                )
        except HTTPException as e:
            base_status = e.status_code

        child_login = "decommission_guard_child"
        child_request = _fake_request(child_login)

        await _forked_key(
            session_factory,
            cern_login=child_login,
            subsystem="ugt",
            node="l1_menu",
            mode_name="guard_child_source_mode",
            payload="<menu/>",
        )
        source_key_id = await _key_id_by_label(
            session_factory, "ugt/l1_menu/guard_child_source_mode/v1"
        )
        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=source_key_id), child_request, session)
        async with session_factory() as session:
            await commit_changeset(CommitIn(), child_request, session, BackgroundTasks())

        await _forked_key(
            session_factory,
            cern_login=child_login,
            subsystem="ugt",
            node="l1_menu",
            mode_name="guard_child_target_mode",
            payload="<menu/>",
        )

        child_status: int | None = None
        try:
            async with session_factory() as session:
                await stage_edits(
                    [
                        StagedEditIn(
                            subsystem_name="ugt",
                            node_name="l1_menu",
                            mode_name="guard_child_target_mode",
                            base_version=1,
                            proposed_children={"decommissioned_child": source_key_id},
                            comment="should be rejected",
                        )
                    ],
                    child_request,
                    session,
                )
        except HTTPException as e:
            child_status = e.status_code

        return base_status, child_status

    assert asyncio.run(run()) == (400, 400)


@pytest.mark.docker
def test_staging_rejects_archived_mode_edits(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> tuple[int | None, int | None]:
        # Distinct logins: a rejected stage_edits leaves an empty changeset that would collide.
        committed_login = "archive_guard_committed"
        committed_request = _fake_request(committed_login)

        await _forked_key(
            session_factory,
            cern_login=committed_login,
            subsystem="ugt",
            node="l1_menu",
            mode_name="guard_archived_mode",
            payload="<menu/>",
        )
        mode_id = await _mode_id(session_factory, "ugt", "l1_menu", "guard_archived_mode")
        async with session_factory() as session:
            await toggle_archival(ArchivalIn(mode_id=mode_id), committed_request, session)
        async with session_factory() as session:
            await commit_changeset(CommitIn(), committed_request, session, BackgroundTasks())

        committed_status: int | None = None
        try:
            async with session_factory() as session:
                await stage_edits(
                    [
                        StagedEditIn(
                            subsystem_name="ugt",
                            node_name="l1_menu",
                            mode_name="guard_archived_mode",
                            base_version=1,
                            proposed_payload="attempted v2",
                            comment="should be rejected",
                        )
                    ],
                    committed_request,
                    session,
                )
        except HTTPException as e:
            committed_status = e.status_code

        # Same changeset that staged the archival, not yet committed: effective state still bites.
        staged_login = "archive_guard_staged"
        staged_request = _fake_request(staged_login)

        await _forked_key(
            session_factory,
            cern_login=staged_login,
            subsystem="ugt",
            node="l1_menu",
            mode_name="guard_self_archived_mode",
            payload="<menu/>",
        )
        self_mode_id = await _mode_id(session_factory, "ugt", "l1_menu", "guard_self_archived_mode")
        async with session_factory() as session:
            await toggle_archival(ArchivalIn(mode_id=self_mode_id), staged_request, session)

        staged_status: int | None = None
        try:
            async with session_factory() as session:
                await stage_edits(
                    [
                        StagedEditIn(
                            subsystem_name="ugt",
                            node_name="l1_menu",
                            mode_name="guard_self_archived_mode",
                            base_version=1,
                            proposed_payload="attempted v2",
                            comment="should be rejected",
                        )
                    ],
                    staged_request,
                    session,
                )
        except HTTPException as e:
            staged_status = e.status_code

        return committed_status, staged_status

    assert asyncio.run(run()) == (400, 400)


@pytest.mark.docker
def test_retired_descendants_finds_a_grandchild_by_either_cause(
    session_factory: async_sessionmaker[AsyncSession],
):
    """Walks the seeded l1_hlt -> l1_trg -> {ugt,ugmt} containment two levels deep."""

    async def run() -> set[tuple[str, str]]:
        cern_login = "retired_desc"
        request = _fake_request(cern_login)

        root_id = await _key_id_by_label(session_factory, "l1_hlt/conf/default/v1")
        leaf_decom_id = await _key_id_by_label(session_factory, "ugt/conf/default/v1")
        leaf_arch_mode_id = await _mode_id(session_factory, "ugmt", "conf", "default")

        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=leaf_decom_id), request, session)
        async with session_factory() as session:
            await commit_changeset(CommitIn(), request, session, BackgroundTasks())

        async with session_factory() as session:
            await toggle_archival(ArchivalIn(mode_id=leaf_arch_mode_id), request, session)
        async with session_factory() as session:
            await commit_changeset(CommitIn(), request, session, BackgroundTasks())

        async with session_factory() as session:
            found = await _retired_descendants(root_id, session)
            return {(ref.label, ref.reason) for ref in found}

    assert asyncio.run(run()) == {
        ("ugt/conf/default/v1", "decommissioned"),
        ("ugmt/conf/default/v1", "mode_archived"),
    }


@pytest.mark.docker
def test_search_keys_matches_label_and_excludes_external(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> tuple[list[str], list[str]]:
        await _forked_key(
            session_factory,
            cern_login="search_label",
            subsystem="ugt",
            node="l1_menu",
            mode_name="search_label_mode",
            payload="<menu/>",
        )
        await _forked_key(
            session_factory,
            cern_login="search_label",
            subsystem="cms_run",
            node="clock_source",
            mode_name="search_label_mode",
            payload="LHC",
        )
        async with session_factory() as session:
            included = await search_keys(session, q="search_label_mode", field="label")
            excluded = await search_keys(session, q="clock_source", field="label")
        return [h.label for h in included], [h.label for h in excluded]

    included, excluded = asyncio.run(run())
    assert included == ["ugt/l1_menu/search_label_mode/v1"]
    assert excluded == []


@pytest.mark.docker
def test_search_keys_label_with_a_version_bypasses_the_tip_filter(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> tuple[list[str], list[str]]:
        await _forked_key(
            session_factory,
            cern_login="search_version",
            subsystem="ugt",
            node="l1_menu",
            mode_name="search_version_mode",
            payload="v1 payload",
        )
        for v in range(1, 10):
            await _restage_key(
                session_factory,
                cern_login="search_version",
                subsystem="ugt",
                node="l1_menu",
                mode_name="search_version_mode",
                base_version=v,
                payload=f"v{v + 1} payload",
            )
        async with session_factory() as session:
            unversioned = await search_keys(session, q="search_version_mode", field="label")
            # v1 is a substring of v10; pasting the v1 label must not also match v10.
            pasted_old = await search_keys(session, q="search_version_mode/v1", field="label")
        return [h.label for h in unversioned], [h.label for h in pasted_old]

    unversioned, pasted_old = asyncio.run(run())
    assert unversioned == ["ugt/l1_menu/search_version_mode/v10"]
    assert pasted_old == ["ugt/l1_menu/search_version_mode/v1"]


@pytest.mark.docker
def test_search_keys_payload_excludes_external_and_only_the_tip_version(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> list[str]:
        await _forked_key(
            session_factory,
            cern_login="search_payload",
            subsystem="ugt",
            node="l1_menu",
            mode_name="search_payload_mode",
            payload="hello v1",
        )
        await _restage_key(
            session_factory,
            cern_login="search_payload",
            subsystem="ugt",
            node="l1_menu",
            mode_name="search_payload_mode",
            base_version=1,
            payload="HELLO v2",
        )
        await _forked_key(
            session_factory,
            cern_login="search_payload",
            subsystem="cms_run",
            node="clock_source",
            mode_name="search_payload_mode",
            payload="hello external",
        )
        async with session_factory() as session:
            hits = await search_keys(session, q="hello", field="payload")
        return [h.label for h in hits]

    labels = asyncio.run(run())
    assert labels == ["ugt/l1_menu/search_payload_mode/v2"]
