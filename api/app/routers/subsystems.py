from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import Subsystem, Vertex, VertexEdge

router = APIRouter(
    prefix="/subsystems",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["subsystems"],
)


class SubsystemOut(BaseModel):
    id: int
    name: str
    display_name: str | None
    category: str

    model_config = {"from_attributes": True}


class TreeOut(BaseModel):
    id: int
    alias: str
    name: str
    subsystem_id: int
    """True owner of a vertex."""
    category: str | None
    """None for bundles."""
    children: list["TreeOut"] = []

    model_config = {"from_attributes": True}


def _build_tree(
    subsystem_id: int,
    vertices: list[Vertex],
    edges: list[tuple[int, str, Vertex]],
) -> list[TreeOut]:
    """Roots have no in-subsystem parent; recursion stops at the boundary, rendered as a leaf."""
    children_by_parent: dict[int, list[tuple[str, Vertex]]] = {}
    for parent_id, alias, child in edges:
        children_by_parent.setdefault(parent_id, []).append((alias, child))

    has_parent_in_subsystem = {
        child.id for _, _, child in edges if child.subsystem_id == subsystem_id
    }
    roots = sorted((n for n in vertices if n.id not in has_parent_in_subsystem), key=lambda n: n.id)

    def build(alias: str, vertex: Vertex, ancestors: frozenset[int]) -> TreeOut:
        out = TreeOut(
            id=vertex.id,
            alias=alias,
            name=vertex.name,
            subsystem_id=vertex.subsystem_id,
            category=vertex.category,
        )
        if vertex.subsystem_id == subsystem_id and vertex.id not in ancestors:
            out.children = [
                build(child_alias, child, ancestors | {vertex.id})
                for child_alias, child in sorted(
                    children_by_parent.get(vertex.id, []), key=lambda pair: (pair[1].id, pair[0])
                )
            ]
        return out

    return [build(root.name, root, frozenset()) for root in roots]


@router.get("/")
async def list_subsystems(session: SessionDep) -> list[SubsystemOut]:
    """Lists all subsystems."""
    subsystems = await session.scalars(select(Subsystem).order_by(Subsystem.name))
    return [SubsystemOut.model_validate(s) for s in subsystems]


@router.get("/{subsystem_id}/tree")
async def get_subsystem_tree(subsystem_id: int, session: SessionDep) -> list[TreeOut]:
    """Returns a subsystem's vertex hierarchy as a forest. Does not cross subsystem boundaries."""
    vertices = list(
        await session.scalars(select(Vertex).where(Vertex.subsystem_id == subsystem_id))
    )

    child = aliased(Vertex)
    edges = await session.execute(
        select(VertexEdge.parent_vertex_id, VertexEdge.alias, child)
        .join(child, VertexEdge.child_vertex_id == child.id)
        .where(VertexEdge.parent_vertex_id.in_([n.id for n in vertices]))
    )

    return _build_tree(subsystem_id, vertices, list(edges.tuples()))
