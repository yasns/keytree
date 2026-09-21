import asyncio
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AppUser, Mode, Node, StagedArchival, Subsystem
from app.routers.commit import CommitIn, commit_changeset
from app.routers.staging import ArchivalIn, discard_changeset, toggle_archival


def _fake_request(cern_login: str) -> SimpleNamespace:
    claims = {
        "cern_upn": cern_login,
        "name": cern_login,
        "resource_access": {"keytree": {"roles": ["keytree_superuser"]}},
    }
    return SimpleNamespace(state=SimpleNamespace(claims=claims))


async def _seeded_mode(
    session_factory: async_sessionmaker[AsyncSession], *, cern_login: str, mode_name: str
) -> int:
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
        await session.commit()
        return mode.id


@pytest.mark.docker
def test_toggle_archival_stages_then_cancels_on_a_second_click(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> tuple[bool, list]:
        mode_id = await _seeded_mode(
            session_factory, cern_login="archiver_toggle", mode_name="toggle_test"
        )
        request = _fake_request("archiver_toggle")

        async with session_factory() as session:
            staged = await toggle_archival(ArchivalIn(mode_id=mode_id), request, session)
        first_pass = staged.archivals[0].archived if staged.archivals else None

        async with session_factory() as session:
            cancelled = await toggle_archival(ArchivalIn(mode_id=mode_id), request, session)

        return first_pass, cancelled.archivals

    first_pass, archivals_after_cancel = asyncio.run(run())
    assert first_pass is True
    assert archivals_after_cancel == []


@pytest.mark.docker
def test_committing_a_staged_archival_updates_the_mode(
    session_factory: async_sessionmaker[AsyncSession],
):
    """archived_by/archived_at clear together on unarchive."""

    async def run() -> tuple[str | None, object, str | None, object]:
        mode_id = await _seeded_mode(
            session_factory, cern_login="archiver_commit", mode_name="commit_test"
        )
        request = _fake_request("archiver_commit")

        async with session_factory() as session:
            await toggle_archival(ArchivalIn(mode_id=mode_id), request, session)
        async with session_factory() as session:
            await commit_changeset(CommitIn(), request, session, BackgroundTasks())
        async with session_factory() as session:
            archived = await session.get(Mode, mode_id)
            assert archived is not None
            after_archive = (archived.archived_by, archived.archived_at)

        async with session_factory() as session:
            await toggle_archival(ArchivalIn(mode_id=mode_id), request, session)
        async with session_factory() as session:
            await commit_changeset(CommitIn(), request, session, BackgroundTasks())
        async with session_factory() as session:
            unarchived = await session.get(Mode, mode_id)
            assert unarchived is not None
            after_unarchive = (unarchived.archived_by, unarchived.archived_at)

        return (*after_archive, *after_unarchive)

    archived_by, archived_at, unarchived_by, unarchived_at = asyncio.run(run())
    assert archived_by == "archiver_commit"
    assert archived_at is not None
    assert unarchived_by is None
    assert unarchived_at is None


@pytest.mark.docker
def test_discarding_an_open_changeset_clears_its_staged_archival(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> int:
        mode_id = await _seeded_mode(
            session_factory, cern_login="archiver_discard", mode_name="discard_test"
        )
        request = _fake_request("archiver_discard")

        async with session_factory() as session:
            await toggle_archival(ArchivalIn(mode_id=mode_id), request, session)
        async with session_factory() as session:
            await discard_changeset(request, session)
        async with session_factory() as session:
            remaining = (
                await session.scalars(
                    select(StagedArchival).where(StagedArchival.mode_id == mode_id)
                )
            ).all()
            return len(remaining)

    assert asyncio.run(run()) == 0
