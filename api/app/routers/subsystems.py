from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import Namespace, NamespaceEdge, Subsystem

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
    """True owner of a namespace."""
    category: str | None
    """None for bundles."""
    format: str | None
    """None for bundles; also null on external leaves until one gets a real format."""
    children: list["TreeOut"] = []

    model_config = {"from_attributes": True}


def _build_tree(
    subsystem_id: int,
    namespaces: list[Namespace],
    edges: list[tuple[int, str, Namespace]],
) -> list[TreeOut]:
    """Roots have no in-subsystem parent; recursion stops at the boundary, rendered as a leaf."""
    children_by_parent: dict[int, list[tuple[str, Namespace]]] = {}
    for parent_id, alias, child in edges:
        children_by_parent.setdefault(parent_id, []).append((alias, child))

    has_parent_in_subsystem = {
        child.id for _, _, child in edges if child.subsystem_id == subsystem_id
    }
    roots = sorted(
        (n for n in namespaces if n.id not in has_parent_in_subsystem), key=lambda n: n.id
    )

    def build(alias: str, namespace: Namespace, ancestors: frozenset[int]) -> TreeOut:
        out = TreeOut(
            id=namespace.id,
            alias=alias,
            name=namespace.name,
            subsystem_id=namespace.subsystem_id,
            category=namespace.category,
            format=namespace.format,
        )
        if namespace.subsystem_id == subsystem_id and namespace.id not in ancestors:
            out.children = [
                build(child_alias, child, ancestors | {namespace.id})
                for child_alias, child in sorted(
                    children_by_parent.get(namespace.id, []), key=lambda pair: (pair[1].id, pair[0])
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
    """Returns a subsystem's namespace hierarchy as a forest. Does not cross subsystem
    boundaries."""
    namespaces = list(
        await session.scalars(select(Namespace).where(Namespace.subsystem_id == subsystem_id))
    )

    child = aliased(Namespace)
    edges = await session.execute(
        select(NamespaceEdge.parent_namespace_id, NamespaceEdge.alias, child)
        .join(child, NamespaceEdge.child_namespace_id == child.id)
        .where(NamespaceEdge.parent_namespace_id.in_([n.id for n in namespaces]))
    )

    return _build_tree(subsystem_id, namespaces, list(edges.tuples()))
