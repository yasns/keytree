import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.authz import require_writable, subsystems_of_modes, writable_subsystems
from app.db.models import Mode, Namespace, Subsystem


def _claims(roles: list[str]) -> dict[str, object]:
    return {"resource_access": {"keytree": {"roles": roles}}}


@pytest.mark.docker
def test_writable_subsystems_resolves_the_grant_matrix(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> set[str]:
        async with session_factory() as session:
            return await writable_subsystems(_claims(["keytree_ugt_expert"]), session)

    assert asyncio.run(run()) == {"ugt"}


@pytest.mark.docker
def test_writable_subsystems_is_empty_for_an_unseeded_role_name(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> set[str]:
        async with session_factory() as session:
            return await writable_subsystems(_claims(["admin"]), session)

    assert asyncio.run(run()) == set()


@pytest.mark.docker
def test_writable_subsystems_short_circuits_on_no_roles(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> set[str]:
        async with session_factory() as session:
            return await writable_subsystems(_claims([]), session)

    assert asyncio.run(run()) == set()


@pytest.mark.docker
def test_require_writable_raises_403_outside_the_grant(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> None:
        async with session_factory() as session:
            await require_writable({"calol2"}, _claims(["keytree_ugt_expert"]), session)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.status_code == 403


@pytest.mark.docker
def test_require_writable_passes_inside_the_grant(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> None:
        async with session_factory() as session:
            await require_writable({"ugt"}, _claims(["keytree_ugt_expert"]), session)

    asyncio.run(run())  # doesn't raise


@pytest.mark.docker
def test_subsystems_of_modes_resolves_a_seeded_mode(
    session_factory: async_sessionmaker[AsyncSession],
):
    async def run() -> set[str]:
        async with session_factory() as session:
            mode_id = await session.scalar(
                select(Mode.id)
                .join(Namespace, Namespace.id == Mode.namespace_id)
                .join(Subsystem, Subsystem.id == Namespace.subsystem_id)
                .where(Subsystem.name == "cms_run", Namespace.name == "clock_source")
            )
            assert mode_id is not None
            return await subsystems_of_modes({mode_id}, session)

    assert asyncio.run(run()) == {"cms_run"}
