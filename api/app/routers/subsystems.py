from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import Node, NodeEdge, Subsystem

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
    """True owner of a node."""
    category: str | None
    """None for bundles."""
    children: list["TreeOut"] = []

    model_config = {"from_attributes": True}


def _build_tree(
    subsystem_id: int,
    nodes: list[Node],
    edges: list[tuple[int, str, Node]],
) -> list[TreeOut]:
    """Roots = no parent in-subsystem; recursion stops at the boundary, far side rendered as a
    leaf."""
    children_by_parent: dict[int, list[tuple[str, Node]]] = {}
    for parent_id, alias, child in edges:
        children_by_parent.setdefault(parent_id, []).append((alias, child))

    has_parent_in_subsystem = {
        child.id for _, _, child in edges if child.subsystem_id == subsystem_id
    }
    roots = sorted((n for n in nodes if n.id not in has_parent_in_subsystem), key=lambda n: n.id)

    def build(alias: str, node: Node, ancestors: frozenset[int]) -> TreeOut:
        out = TreeOut(
            id=node.id,
            alias=alias,
            name=node.name,
            subsystem_id=node.subsystem_id,
            category=node.category,
        )
        if node.subsystem_id == subsystem_id and node.id not in ancestors:
            out.children = [
                build(child_alias, child, ancestors | {node.id})
                for child_alias, child in sorted(
                    children_by_parent.get(node.id, []), key=lambda pair: (pair[1].id, pair[0])
                )
            ]
        return out

    return [build(root.name, root, frozenset()) for root in roots]


@router.get("/")
async def list_subsystems(session: SessionDep) -> list[SubsystemOut]:
    """Lists all active subsystems."""
    subsystems = await session.scalars(
        select(Subsystem).where(Subsystem.retired_at.is_(None)).order_by(Subsystem.name)
    )
    return [SubsystemOut.model_validate(s) for s in subsystems]


@router.get("/{subsystem_id}/tree")
async def get_subsystem_tree(subsystem_id: int, session: SessionDep) -> list[TreeOut]:
    """Returns a subsystem's node hierarchy as a forest. Does not cross subsystem boundaries."""
    nodes = list(
        await session.scalars(
            select(Node).where(Node.subsystem_id == subsystem_id, Node.retired_at.is_(None))
        )
    )

    child = aliased(Node)
    edges = await session.execute(
        select(NodeEdge.parent_node_id, NodeEdge.alias, child)
        .join(child, NodeEdge.child_node_id == child.id)
        .where(NodeEdge.parent_node_id.in_([n.id for n in nodes]), child.retired_at.is_(None))
    )

    return _build_tree(subsystem_id, nodes, list(edges.tuples()))
