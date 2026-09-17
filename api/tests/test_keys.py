import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Changeset, Key, Mode, Node, StagedEdit, Subsystem
from app.routers.commit import CommitIn, commit_changeset
from app.routers.keys import _build_child_meta, _build_key_detail, search_keys
from app.routers.staging import StagedEditIn, stage_edits
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
    out = _build_key_detail(_key(), "Jane Doe", "default", 3, "ugt/l1_menu/default/v3")

    assert out.created_by_display_name == "Jane Doe"
    assert out.based_on is not None
    assert out.based_on.mode_name == "default"
    assert out.based_on.version == 3
    assert out.based_on.label == "ugt/l1_menu/default/v3"


def test_build_key_detail_has_no_ancestor_without_fork_source_or_prior_version():
    out = _build_key_detail(_key(), "Jane Doe", None, None, None)

    assert out.based_on is None


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
        changeset = Changeset(created_by=cern_login, comment="")
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
        await commit_changeset(CommitIn(comment="seed"), _fake_request(cern_login), session)


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
        await commit_changeset(CommitIn(comment="restage"), request, session)


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
