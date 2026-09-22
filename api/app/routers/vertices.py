from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import AppUser, Key, Mode, Subsystem, Vertex

router = APIRouter(
    prefix="/vertices",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["vertices"],
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
    decommissioned_versions: list[int]
    """Subset of `versions` that are decommissioned."""

    model_config = {"from_attributes": True}


class VertexOut(BaseModel):
    id: int
    name: str
    category: str | None
    """None for bundles."""
    subsystem_id: int
    subsystem_name: str
    modes: list[ModeOut]

    model_config = {"from_attributes": True}


def _build_vertex_detail(
    vertex: Vertex,
    subsystem_name: str,
    modes: list[Mode],
    keys: list[Key],
    display_names: dict[str, str],
) -> VertexOut:
    versions_by_mode: dict[int, list[int]] = {}
    decommissioned_versions_by_mode: dict[int, list[int]] = {}
    for key in keys:
        versions_by_mode.setdefault(key.mode_id, []).append(key.version)
        if key.decommissioned_at is not None:
            decommissioned_versions_by_mode.setdefault(key.mode_id, []).append(key.version)
    for versions in versions_by_mode.values():
        versions.sort(reverse=True)

    return VertexOut(
        id=vertex.id,
        name=vertex.name,
        category=vertex.category,
        subsystem_id=vertex.subsystem_id,
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
                decommissioned_versions=decommissioned_versions_by_mode.get(mode.id, []),
            )
            for mode in sorted(modes, key=lambda m: m.name.lower())
        ],
    )


async def _vertex_detail_or_404(vertex: Vertex | None, session: SessionDep) -> VertexOut:
    if vertex is None:
        raise HTTPException(status_code=404, detail="vertex not found")

    subsystem_name = await session.scalar(
        select(Subsystem.name).where(Subsystem.id == vertex.subsystem_id)
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
            .where(Mode.vertex_id == vertex.id)
        )
    ).all()
    modes = [row[0] for row in mode_rows]
    display_names = {row[0].created_by: row[1] for row in mode_rows} | {
        row[0].archived_by: row[2] for row in mode_rows if row[0].archived_by is not None
    }

    keys = list(await session.scalars(select(Key).where(Key.mode_id.in_([m.id for m in modes]))))

    return _build_vertex_detail(vertex, subsystem_name, modes, keys, display_names)


@router.get("/by-path/{subsystem_name}/{vertex_name}")
async def get_vertex_by_path(
    subsystem_name: str, vertex_name: str, session: SessionDep
) -> VertexOut:
    """Fetches a vertex by (subsystem, name)."""
    vertex = await session.scalar(
        select(Vertex)
        .join(Subsystem, Subsystem.id == Vertex.subsystem_id)
        .where(Subsystem.name == subsystem_name, Vertex.name == vertex_name)
    )
    return await _vertex_detail_or_404(vertex, session)


@router.get("/{vertex_id}")
async def get_vertex(vertex_id: int, session: SessionDep) -> VertexOut:
    """Fetches a single vertex by numeric id."""
    vertex = await session.get(Vertex, vertex_id)
    return await _vertex_detail_or_404(vertex, session)
