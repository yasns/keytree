from typing import cast

from fastapi import HTTPException
from sqlalchemy import select

from app.db.base import SessionDep
from app.db.models import Mode, Node, Role, RoleSubsystem, Subsystem


def claim_roles(claims: dict[str, object]) -> list[str]:
    resource_access = cast("dict[str, object]", claims.get("resource_access", {}))
    keytree_access = cast("dict[str, object]", resource_access.get("keytree", {}))
    return cast("list[str]", keytree_access.get("roles", []))


async def writable_subsystems(claims: dict[str, object], session: SessionDep) -> set[str]:
    roles = claim_roles(claims)
    if not roles:
        return set()
    rows = await session.scalars(
        select(Subsystem.name)
        .join(RoleSubsystem, RoleSubsystem.subsystem_id == Subsystem.id)
        .join(Role, Role.id == RoleSubsystem.role_id)
        .where(Role.name.in_(roles))
    )
    return set(rows)


async def subsystems_of_modes(mode_ids: set[int], session: SessionDep) -> set[str]:
    if not mode_ids:
        return set()
    rows = await session.scalars(
        select(Subsystem.name)
        .select_from(Mode)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .where(Mode.id.in_(mode_ids))
    )
    return set(rows)


async def require_writable(
    wanted: set[str], claims: dict[str, object], session: SessionDep
) -> None:
    missing = wanted - await writable_subsystems(claims, session)
    if missing:
        raise HTTPException(
            status_code=403, detail=f"no write access to subsystem: {', '.join(sorted(missing))}"
        )
