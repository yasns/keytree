from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import AppUser, Key, Mode, Node, Subsystem

router = APIRouter(
    prefix="/nodes",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["nodes"],
)


class ModeOut(BaseModel):
    id: int
    name: str
    description: str
    created_by: str
    created_by_display_name: str
    created_at: datetime
    archived_by: str | None
    """None while active."""
    archived_by_display_name: str | None
    """None while active."""
    archived_at: datetime | None
    """None while active."""
    versions: list[int]
    """Newest first."""

    model_config = {"from_attributes": True}


class NodeOut(BaseModel):
    id: int
    name: str
    category: str | None
    """None for bundles."""
    subsystem_id: int
    subsystem_name: str
    modes: list[ModeOut]

    model_config = {"from_attributes": True}


def _build_node_detail(
    node: Node,
    subsystem_name: str,
    modes: list[Mode],
    keys: list[Key],
    display_names: dict[str, str],
) -> NodeOut:
    versions_by_mode: dict[int, list[int]] = {}
    for key in keys:
        versions_by_mode.setdefault(key.mode_id, []).append(key.version)
    for versions in versions_by_mode.values():
        versions.sort(reverse=True)

    return NodeOut(
        id=node.id,
        name=node.name,
        category=node.category,
        subsystem_id=node.subsystem_id,
        subsystem_name=subsystem_name,
        modes=[
            ModeOut(
                id=mode.id,
                name=mode.name,
                description=mode.description,
                created_by=mode.created_by,
                created_by_display_name=display_names[mode.created_by],
                created_at=mode.created_at,
                archived_by=mode.archived_by,
                archived_by_display_name=(
                    display_names[mode.archived_by] if mode.archived_by is not None else None
                ),
                archived_at=mode.archived_at,
                versions=versions_by_mode.get(mode.id, []),
            )
            for mode in sorted(modes, key=lambda m: m.id)
        ],
    )


async def _node_detail_or_404(node: Node | None, session: SessionDep) -> NodeOut:
    if node is None or node.retired_at is not None:
        raise HTTPException(status_code=404, detail="node not found")

    subsystem_name = await session.scalar(
        select(Subsystem.name).where(Subsystem.id == node.subsystem_id)
    )
    assert subsystem_name is not None

    creator = aliased(AppUser)
    archiver = aliased(AppUser)
    mode_rows = (
        await session.execute(
            select(Mode, creator.display_name, archiver.display_name)
            .select_from(Mode)
            .outerjoin(creator, creator.cern_login == Mode.created_by)
            .outerjoin(archiver, archiver.cern_login == Mode.archived_by)
            .where(Mode.node_id == node.id)
        )
    ).all()
    modes = [row[0] for row in mode_rows]
    display_names = {row[0].created_by: row[1] for row in mode_rows} | {
        row[0].archived_by: row[2] for row in mode_rows if row[0].archived_by is not None
    }

    keys = list(await session.scalars(select(Key).where(Key.mode_id.in_([m.id for m in modes]))))

    return _build_node_detail(node, subsystem_name, modes, keys, display_names)


@router.get("/by-path/{subsystem_name}/{node_name}")
async def get_node_by_path(subsystem_name: str, node_name: str, session: SessionDep) -> NodeOut:
    """Fetches a node by (subsystem, name)."""
    node = await session.scalar(
        select(Node)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .where(Subsystem.name == subsystem_name, Node.name == node_name)
    )
    return await _node_detail_or_404(node, session)


@router.get("/{node_id}")
async def get_node(node_id: int, session: SessionDep) -> NodeOut:
    """Fetches a single node by numeric id."""
    node = await session.get(Node, node_id)
    return await _node_detail_or_404(node, session)
