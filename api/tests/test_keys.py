import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    Changeset,
    Key,
    Mode,
    StagedDecommission,
    StagedEdit,
    Subsystem,
    Vertex,
)
from app.routers.commit import commit_changeset
from app.routers.keys import (
    AggregateOut,
    KeyVersion,
    RetiredRefOut,
    _build_child_meta,
    _build_key_detail,
    _retired_descendants,
    aggregate_key,
    search_keys,
)
from app.routers.staging import (
    ArchivalIn,
    CopyIn,
    DecommissionIn,
    ForkIn,
    StagedEditIn,
    copy_to_mode,
    discard_changeset,
    fork_mode,
    stage_edits,
    toggle_archival,
    toggle_decommission,
)
from app.routers.user import upsert_app_user


def _key() -> Key:
    return Key(
        id=9,
        mode_id=3,
        vertex_id=42,
        version=2,
        label="ugt/l1_menu/default/v2",
        payload="menu contents",
        staged_edit_id=1,
        created_by="jdoe",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        comment="new menu",
        validation_status="skipped",
    )


def test_version_path_param_accepts_the_label_v_prefix():
    adapter = TypeAdapter(KeyVersion)

    assert adapter.validate_python("v12") == 12
    assert adapter.validate_python("12") == 12
    with pytest.raises(ValidationError):
        adapter.validate_python("draft")


def test_build_child_meta_fills_key_fields():
    meta = _build_child_meta(("l1_menu", _key(), 42, "l1_menu", "ugt", "menu", "yaml", "default"))

    assert meta.id == 9
    assert meta.label == "ugt/l1_menu/default/v2"
    assert meta.format == "yaml"
    assert meta.mode_name == "default"
    assert meta.version == 2
    assert meta.created_by == "jdoe"
    # Payload is only carried for external children
    assert meta.payload is None


def test_build_child_meta_carries_external_payload():
    meta = _build_child_meta(
        ("clock", _key(), 7, "clock_source", "cms_run", "external", None, "default")
    )

    assert meta.payload == "menu contents"


def test_build_child_meta_lists_empty_alias_with_null_key():
    meta = _build_child_meta(("l1_menu", None, 42, "l1_menu", "ugt", "menu", "yaml", None))

    assert meta.alias == "l1_menu"
    # structural fields come off the edge: row still renders/refills
    assert meta.vertex_id == 42
    assert meta.vertex_name == "l1_menu"
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
    vertex: str,
    mode_name: str,
    payload: str,
) -> None:
    """Fresh mode on a seeded vertex, committed straight to v1 with `payload`."""
    async with session_factory() as session:
        await upsert_app_user({"cern_upn": cern_login, "name": cern_login}, session)
        vertex_id = await session.scalar(
            select(Vertex.id)
            .join(Subsystem, Subsystem.id == Vertex.subsystem_id)
            .where(Subsystem.name == subsystem, Vertex.name == vertex)
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
                proposed_payload=payload,
                comment="seed",
                validation_status="skipped",
            )
        )
        await session.commit()
    async with session_factory() as session:
        await commit_changeset(_fake_request(cern_login), session, BackgroundTasks())


async def _restage_key(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    cern_login: str,
    subsystem: str,
    vertex: str,
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
                    vertex_name=vertex,
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
        await commit_changeset(request, session, BackgroundTasks())


async def _key_id_by_label(session_factory: async_sessionmaker[AsyncSession], label: str) -> int:
    async with session_factory() as session:
        key_id = await session.scalar(select(Key.id).where(Key.label == label))
        assert key_id is not None
        return key_id


async def _mode_id(
    session_factory: async_sessionmaker[AsyncSession], subsystem: str, vertex: str, mode_name: str
) -> int:
    async with session_factory() as session:
        mode_id = await session.scalar(
            select(Mode.id)
            .join(Vertex, Vertex.id == Mode.vertex_id)
            .join(Subsystem, Subsystem.id == Vertex.subsystem_id)
            .where(Subsystem.name == subsystem, Vertex.name == vertex, Mode.name == mode_name)
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
            vertex="l1_menu",
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
            vertex="l1_menu",
            mode_name="decommission_commit_mode",
            payload="<menu/>",
        )
        key_id = await _key_id_by_label(session_factory, "ugt/l1_menu/decommission_commit_mode/v1")
        request = _fake_request("decommission_commit")

        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=key_id), request, session)
        async with session_factory() as session:
            await commit_changeset(request, session, BackgroundTasks())
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
            await commit_changeset(request, session, BackgroundTasks())
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
            vertex="l1_menu",
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
            vertex="l1_menu",
            mode_name="guard_base_mode",
            payload="<menu/>",
        )
        base_key_id = await _key_id_by_label(session_factory, "ugt/l1_menu/guard_base_mode/v1")
        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=base_key_id), base_request, session)
        async with session_factory() as session:
            await commit_changeset(base_request, session, BackgroundTasks())

        base_status: int | None = None
        try:
            async with session_factory() as session:
                await stage_edits(
                    [
                        StagedEditIn(
                            subsystem_name="ugt",
                            vertex_name="l1_menu",
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
            vertex="l1_menu",
            mode_name="guard_child_source_mode",
            payload="<menu/>",
        )
        source_key_id = await _key_id_by_label(
            session_factory, "ugt/l1_menu/guard_child_source_mode/v1"
        )
        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=source_key_id), child_request, session)
        async with session_factory() as session:
            await commit_changeset(child_request, session, BackgroundTasks())

        await _forked_key(
            session_factory,
            cern_login=child_login,
            subsystem="ugt",
            vertex="l1_menu",
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
                            vertex_name="l1_menu",
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
            vertex="l1_menu",
            mode_name="guard_archived_mode",
            payload="<menu/>",
        )
        mode_id = await _mode_id(session_factory, "ugt", "l1_menu", "guard_archived_mode")
        async with session_factory() as session:
            await toggle_archival(ArchivalIn(mode_id=mode_id), committed_request, session)
        async with session_factory() as session:
            await commit_changeset(committed_request, session, BackgroundTasks())

        committed_status: int | None = None
        try:
            async with session_factory() as session:
                await stage_edits(
                    [
                        StagedEditIn(
                            subsystem_name="ugt",
                            vertex_name="l1_menu",
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
            vertex="l1_menu",
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
                            vertex_name="l1_menu",
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
            await commit_changeset(request, session, BackgroundTasks())

        async with session_factory() as session:
            await toggle_archival(ArchivalIn(mode_id=leaf_arch_mode_id), request, session)
        async with session_factory() as session:
            await commit_changeset(request, session, BackgroundTasks())

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
            vertex="l1_menu",
            mode_name="search_label_mode",
            payload="<menu/>",
        )
        await _forked_key(
            session_factory,
            cern_login="search_label",
            subsystem="cms_run",
            vertex="clock_source",
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
            vertex="l1_menu",
            mode_name="search_version_mode",
            payload="v1 payload",
        )
        for v in range(1, 10):
            await _restage_key(
                session_factory,
                cern_login="search_version",
                subsystem="ugt",
                vertex="l1_menu",
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
            vertex="l1_menu",
            mode_name="search_payload_mode",
            payload="hello v1",
        )
        await _restage_key(
            session_factory,
            cern_login="search_payload",
            subsystem="ugt",
            vertex="l1_menu",
            mode_name="search_payload_mode",
            base_version=1,
            payload="HELLO v2",
        )
        await _forked_key(
            session_factory,
            cern_login="search_payload",
            subsystem="cms_run",
            vertex="clock_source",
            mode_name="search_payload_mode",
            payload="hello external",
        )
        async with session_factory() as session:
            hits = await search_keys(session, q="hello", field="payload")
        return [h.label for h in hits]

    labels = asyncio.run(run())
    assert labels == ["ugt/l1_menu/search_payload_mode/v2"]


@pytest.mark.docker
def test_restaging_the_original_payload_undoes_the_staged_edit(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> list[str]:
        await _forked_key(
            session_factory,
            cern_login="restage_to_baseline",
            subsystem="ugt",
            vertex="l1_menu",
            mode_name="restage_to_baseline_mode",
            payload="<menu/>",
        )
        request = _fake_request("restage_to_baseline")
        async with session_factory() as session:
            changeset = await stage_edits(
                [
                    StagedEditIn(
                        subsystem_name="ugt",
                        vertex_name="l1_menu",
                        mode_name="restage_to_baseline_mode",
                        base_version=1,
                        proposed_payload="<menu/>",
                        comment="no-op",
                    )
                ],
                request,
                session,
            )
        return [e.mode_name for e in changeset.edits]

    assert asyncio.run(run()) == []


@pytest.mark.docker
def test_staging_rejects_a_child_whose_mode_is_archived(
    session_factory: async_sessionmaker[AsyncSession],
):
    """The archival counterpart of the decommissioned-child guard, committed and staged alike."""

    async def run() -> tuple[int | None, int | None]:
        statuses: list[int | None] = []
        for login, source_mode, target_mode, commit_archival in (
            ("child_arch_committed", "child_arch_src_a", "child_arch_tgt_a", True),
            ("child_arch_staged", "child_arch_src_b", "child_arch_tgt_b", False),
        ):
            request = _fake_request(login)
            for mode_name in (source_mode, target_mode):
                await _forked_key(
                    session_factory,
                    cern_login=login,
                    subsystem="ugt",
                    vertex="l1_menu",
                    mode_name=mode_name,
                    payload="<menu/>",
                )
            source_key_id = await _key_id_by_label(session_factory, f"ugt/l1_menu/{source_mode}/v1")
            source_mode_id = await _mode_id(session_factory, "ugt", "l1_menu", source_mode)

            async with session_factory() as session:
                await toggle_archival(ArchivalIn(mode_id=source_mode_id), request, session)
            if commit_archival:
                async with session_factory() as session:
                    await commit_changeset(request, session, BackgroundTasks())

            status: int | None = None
            try:
                async with session_factory() as session:
                    await stage_edits(
                        [
                            StagedEditIn(
                                subsystem_name="ugt",
                                vertex_name="l1_menu",
                                mode_name=target_mode,
                                base_version=1,
                                proposed_children={"archived_child": source_key_id},
                                comment="should be rejected",
                            )
                        ],
                        request,
                        session,
                    )
            except HTTPException as e:
                status = e.status_code
            statuses.append(status)

        return statuses[0], statuses[1]

    assert asyncio.run(run()) == (400, 400)


@pytest.mark.docker
def test_toggle_archival_rejects_a_mode_still_referenced_by_staged_edits(
    session_factory: async_sessionmaker[AsyncSession],
):
    """Reverse direction: the reference is staged first, then the archival is queued."""

    async def run() -> tuple[int | None, int | None]:
        child_login = "arch_rev_child"
        child_request = _fake_request(child_login)
        for mode_name in ("arch_rev_src", "arch_rev_parent"):
            await _forked_key(
                session_factory,
                cern_login=child_login,
                subsystem="ugt",
                vertex="l1_menu",
                mode_name=mode_name,
                payload="<menu/>",
            )
        source_key_id = await _key_id_by_label(session_factory, "ugt/l1_menu/arch_rev_src/v1")
        source_mode_id = await _mode_id(session_factory, "ugt", "l1_menu", "arch_rev_src")

        async with session_factory() as session:
            await stage_edits(
                [
                    StagedEditIn(
                        subsystem_name="ugt",
                        vertex_name="l1_menu",
                        mode_name="arch_rev_parent",
                        base_version=1,
                        proposed_children={"live_child": source_key_id},
                        comment="references the mode about to be archived",
                    )
                ],
                child_request,
                session,
            )

        child_status: int | None = None
        try:
            async with session_factory() as session:
                await toggle_archival(ArchivalIn(mode_id=source_mode_id), child_request, session)
        except HTTPException as e:
            child_status = e.status_code

        # An edit *on* the mode being archived is just as contradictory as one referencing it.
        self_login = "arch_rev_self"
        self_request = _fake_request(self_login)
        await _forked_key(
            session_factory,
            cern_login=self_login,
            subsystem="ugt",
            vertex="l1_menu",
            mode_name="arch_rev_self",
            payload="<menu/>",
        )
        self_mode_id = await _mode_id(session_factory, "ugt", "l1_menu", "arch_rev_self")
        async with session_factory() as session:
            await stage_edits(
                [
                    StagedEditIn(
                        subsystem_name="ugt",
                        vertex_name="l1_menu",
                        mode_name="arch_rev_self",
                        base_version=1,
                        proposed_payload="v2",
                        comment="new version on the mode about to be archived",
                    )
                ],
                self_request,
                session,
            )

        self_status: int | None = None
        try:
            async with session_factory() as session:
                await toggle_archival(ArchivalIn(mode_id=self_mode_id), self_request, session)
        except HTTPException as e:
            self_status = e.status_code

        return child_status, self_status

    assert asyncio.run(run()) == (400, 400)


@pytest.mark.docker
def test_toggle_decommission_rejects_a_key_still_referenced_by_a_staged_edit(
    session_factory: async_sessionmaker[AsyncSession],
):
    """Previously this slipped past the toggle and only surfaced as a 409 at commit."""

    async def run() -> int | None:
        login = "decom_rev"
        request = _fake_request(login)
        for mode_name in ("decom_rev_src", "decom_rev_parent"):
            await _forked_key(
                session_factory,
                cern_login=login,
                subsystem="ugt",
                vertex="l1_menu",
                mode_name=mode_name,
                payload="<menu/>",
            )
        source_key_id = await _key_id_by_label(session_factory, "ugt/l1_menu/decom_rev_src/v1")

        async with session_factory() as session:
            await stage_edits(
                [
                    StagedEditIn(
                        subsystem_name="ugt",
                        vertex_name="l1_menu",
                        mode_name="decom_rev_parent",
                        base_version=1,
                        proposed_children={"live_child": source_key_id},
                        comment="references the key about to be decommissioned",
                    )
                ],
                request,
                session,
            )

        try:
            async with session_factory() as session:
                await toggle_decommission(DecommissionIn(key_id=source_key_id), request, session)
        except HTTPException as e:
            return e.status_code
        return None

    assert asyncio.run(run()) == 400


@pytest.mark.docker
def test_staged_unretirement_lets_a_reference_be_staged_again(
    session_factory: async_sessionmaker[AsyncSession],
):
    """Relaxing is never blocked, and a staged toggle overrides committed state both ways."""

    async def run() -> tuple[int, int]:
        counts: list[int] = []
        for login, source_mode, parent_mode, archive in (
            ("relax_arch", "relax_arch_src", "relax_arch_parent", True),
            ("relax_decom", "relax_decom_src", "relax_decom_parent", False),
        ):
            request = _fake_request(login)
            for mode_name in (source_mode, parent_mode):
                await _forked_key(
                    session_factory,
                    cern_login=login,
                    subsystem="ugt",
                    vertex="l1_menu",
                    mode_name=mode_name,
                    payload="<menu/>",
                )
            source_key_id = await _key_id_by_label(session_factory, f"ugt/l1_menu/{source_mode}/v1")
            source_mode_id = await _mode_id(session_factory, "ugt", "l1_menu", source_mode)

            # Retire it, commit, then queue the reverse toggle in a fresh changeset.
            for _ in range(2):
                async with session_factory() as session:
                    if archive:
                        await toggle_archival(ArchivalIn(mode_id=source_mode_id), request, session)
                    else:
                        await toggle_decommission(
                            DecommissionIn(key_id=source_key_id), request, session
                        )
                if _ == 0:
                    async with session_factory() as session:
                        await commit_changeset(request, session, BackgroundTasks())

            async with session_factory() as session:
                changeset = await stage_edits(
                    [
                        StagedEditIn(
                            subsystem_name="ugt",
                            vertex_name="l1_menu",
                            mode_name=parent_mode,
                            base_version=1,
                            proposed_children={"revived_child": source_key_id},
                            comment="allowed by the staged unretirement",
                        )
                    ],
                    request,
                    session,
                )
            counts.append(len(changeset.edits))

        return counts[0], counts[1]

    assert asyncio.run(run()) == (1, 1)


@pytest.mark.docker
def test_fork_and_copy_guard_children_but_allow_an_archived_source(
    session_factory: async_sessionmaker[AsyncSession],
):
    """Forking out of an archived mode is the only migration path off it, so it stays allowed."""

    async def run() -> tuple[int, int | None, int | None]:
        login = "fork_guard"
        request = _fake_request(login)
        for mode_name in ("fork_guard_arch", "fork_guard_retired", "fork_guard_healthy"):
            await _forked_key(
                session_factory,
                cern_login=login,
                subsystem="ugt",
                vertex="l1_menu",
                mode_name=mode_name,
                payload="<menu/>",
            )
        arch_mode_id = await _mode_id(session_factory, "ugt", "l1_menu", "fork_guard_arch")
        retired_key_id = await _key_id_by_label(
            session_factory, "ugt/l1_menu/fork_guard_retired/v1"
        )

        async with session_factory() as session:
            await toggle_archival(ArchivalIn(mode_id=arch_mode_id), request, session)
        async with session_factory() as session:
            await toggle_decommission(DecommissionIn(key_id=retired_key_id), request, session)
        async with session_factory() as session:
            await commit_changeset(request, session, BackgroundTasks())

        async with session_factory() as session:
            changeset = await fork_mode(
                ForkIn(
                    subsystem_name="ugt",
                    vertex_name="l1_menu",
                    mode_name="fork_guard_arch",
                    base_version=1,
                    new_mode_name="fork_guard_revived",
                    description="revived off an archived mode",
                    proposed_payload="<menu/>",
                    comment="allowed",
                ),
                request,
                session,
            )
        forked = len(changeset.edits)

        fork_status: int | None = None
        try:
            async with session_factory() as session:
                await fork_mode(
                    ForkIn(
                        subsystem_name="ugt",
                        vertex_name="l1_menu",
                        mode_name="fork_guard_healthy",
                        base_version=1,
                        new_mode_name="fork_guard_rejected",
                        description="pins a decommissioned child",
                        proposed_children={"retired_child": retired_key_id},
                        comment="should be rejected",
                    ),
                    request,
                    session,
                )
        except HTTPException as e:
            fork_status = e.status_code

        copy_status: int | None = None
        try:
            async with session_factory() as session:
                await copy_to_mode(
                    CopyIn(
                        subsystem_name="ugt",
                        vertex_name="l1_menu",
                        mode_name="fork_guard_healthy",
                        base_version=1,
                        target_mode_name="fork_guard_revived",
                        proposed_children={"retired_child": retired_key_id},
                        comment="should be rejected",
                    ),
                    request,
                    session,
                )
        except HTTPException as e:
            copy_status = e.status_code

        return forked, fork_status, copy_status

    assert asyncio.run(run()) == (1, 400, 400)


def _flatten(node: AggregateOut, prefix: str = "") -> dict[str, tuple[str | None, str | None]]:
    """Alias path -> (label, format), the root sitting at the empty path."""
    flat = {prefix: (node.label, node.format)}
    for child in node.children:
        assert child.alias is not None
        flat |= _flatten(child, f"{prefix}/{child.alias}" if prefix else child.alias)
    return flat


@pytest.mark.docker
def test_aggregate_nests_every_seeded_payload_under_the_root(
    session_factory: async_sessionmaker[AsyncSession],
):
    """Crosses subsystem boundaries and reaches leaves several levels down."""

    async def run() -> dict[str, tuple[str | None, str | None]]:
        async with session_factory() as session:
            return _flatten(await aggregate_key("l1_hlt", "conf", "default", 1, session))

    flat = asyncio.run(run())

    assert flat[""] == ("l1_hlt/conf/default/v1", None)
    assert flat["hlt_key"] == ("l1_hlt/hlt_key/default/v1", None)
    # l1_hlt -> l1_trg -> ugt -> l1_menu, crossing three subsystem boundaries
    assert flat["l1_trg_conf/ugt_conf"] == ("ugt/conf/default/v1", None)
    assert flat["l1_trg_conf/ugt_conf/l1_menu"] == ("ugt/l1_menu/default/v1", "yaml")
    assert flat["l1_trg_conf/tcds/ugt/pi"] == ("tcds/pi/default/v1", "plaintext")
    # format is per-leaf, not per-tree: cppf is xml where its siblings are yaml
    assert flat["l1_trg_conf/cppf_conf/algo"] == ("cppf/algo/default/v1", "xml")
    # ugt/rs is pointed at under two aliases; both expand, and neither recurses forever
    assert flat["l1_trg_rs/ugt_rs"] == flat["l1_trg_rs/spare_ugt_rs"] == ("ugt/rs/default/v1", None)
    assert flat["l1_trg_rs/spare_ugt_rs/rs_mp7"] == ("ugt/rs_mp7/default/v1", "yaml")


@pytest.mark.docker
def test_aggregate_emits_an_emptied_alias_as_a_null_node(
    session_factory: async_sessionmaker[AsyncSession],
):
    """An alias with no key_child row is a slot to be filled, not an error."""

    async def run() -> dict[str, tuple[str | None, str | None]]:
        cern_login = "aggregate_empty"
        mode_name = "aggregate_empty_mode"
        async with session_factory() as session:
            await upsert_app_user({"cern_upn": cern_login, "name": cern_login}, session)
            vertex_id = await session.scalar(
                select(Vertex.id)
                .join(Subsystem, Subsystem.id == Vertex.subsystem_id)
                .where(Subsystem.name == "ugt", Vertex.name == "conf")
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
                    proposed_children={},
                    comment="every alias left empty",
                    validation_status="skipped",
                )
            )
            await session.commit()
        async with session_factory() as session:
            await commit_changeset(_fake_request(cern_login), session, BackgroundTasks())
        async with session_factory() as session:
            return _flatten(await aggregate_key("ugt", "conf", mode_name, 1, session))

    flat = asyncio.run(run())

    assert flat[""] == ("ugt/conf/aggregate_empty_mode/v1", None)
    # the slot still advertises the format its eventual occupant must use
    assert flat["l1_menu"] == (None, "yaml")
    assert sorted(flat) == ["", "algo", "hw", "infra", "l1_menu"]
    assert all(label is None for path, (label, _) in flat.items() if path)
