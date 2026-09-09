from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.orm import aliased
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import Key, KeyChild, Mode, Node, NodeEdge, Subsystem

router = APIRouter(
    prefix="/keys",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["keys"],
)


class KeyOut(BaseModel):
    id: int
    label: str
    version: int
    payload: str | None
    """None for bundles."""
    created_by: str
    created_at: datetime
    comment: str

    model_config = {"from_attributes": True}


class KeyChildMetaOut(BaseModel):
    id: int | None
    alias: str
    label: str | None
    node_id: int
    node_name: str
    subsystem_name: str
    category: str | None
    """None for bundles."""
    payload: str | None
    """Only populated for external children."""
    mode_name: str | None
    version: int | None
    created_by: str | None
    created_at: datetime | None
    comment: str | None


_KeyLocator = tuple[str, str, str, int]
"""(subsystem_name, node_name, mode_name, version)."""


async def keys_or_404(locators: list[_KeyLocator], session: SessionDep) -> list[Key]:
    """Resolves multiple (subsystem, node, mode, version) keys in one query, in request order."""
    if not locators:
        return []
    rows = await session.execute(
        select(Subsystem.name, Node.name, Mode.name, Key)
        .select_from(Key)
        .join(Mode, Mode.id == Key.mode_id)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .where(tuple_(Subsystem.name, Node.name, Mode.name, Key.version).in_(locators))
    )
    found = {(s, n, m, key.version): key for s, n, m, key in rows.tuples()}
    keys: list[Key] = []
    for locator in locators:
        key = found.get(locator)
        if key is None:
            raise HTTPException(status_code=404, detail="key not found")
        keys.append(key)
    return keys


async def key_or_404(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> Key:
    [key] = await keys_or_404([(subsystem_name, node_name, mode_name, version)], session)
    return key


@router.get("/{subsystem_name}/{node_name}/{mode_name}/{version}")
async def get_key(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> KeyOut:
    """Fetches a single key by (subsystem, node, mode, version)."""
    key = await key_or_404(subsystem_name, node_name, mode_name, version, session)
    return KeyOut.model_validate(key)


_ChildRow = tuple[str, Key | None, int, str, str, str | None, str | None]


def _build_child_meta(row: _ChildRow) -> KeyChildMetaOut:
    """Builds a child key's metadata row, keeping it in the bundle with a null key if unset."""
    alias, key, node_id, node_name, subsystem_name, category, mode_name = row
    return KeyChildMetaOut(
        id=key.id if key else None,
        alias=alias,
        label=key.label if key else None,
        node_id=node_id,
        node_name=node_name,
        subsystem_name=subsystem_name,
        category=category,
        payload=key.payload if key and category == "external" else None,
        mode_name=mode_name,
        version=key.version if key else None,
        created_by=key.created_by if key else None,
        created_at=key.created_at if key else None,
        comment=key.comment if key else None,
    )


@router.get("/{subsystem_name}/{node_name}/{mode_name}/{version}/children")
async def get_key_children(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> list[KeyChildMetaOut]:
    """Returns one level of a bundle. One row per alias, whether emptied or not. Crosses subsystem
    boundaries freely."""
    parent = await key_or_404(subsystem_name, node_name, mode_name, version, session)

    child = aliased(Key)

    rows = await session.execute(
        select(
            NodeEdge.alias,
            child,
            Node.id,
            Node.name,
            Subsystem.name,
            Node.category,
            Mode.name,
        )
        .select_from(NodeEdge)
        .join(Node, Node.id == NodeEdge.child_node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .outerjoin(
            KeyChild,
            (KeyChild.parent_key_id == parent.id) & (KeyChild.alias == NodeEdge.alias),
        )
        .outerjoin(child, child.id == KeyChild.child_key_id)
        .outerjoin(Mode, Mode.id == child.mode_id)
        .where(NodeEdge.parent_node_id == parent.node_id)
        .order_by(NodeEdge.alias)
    )

    return [_build_child_meta(cast("_ChildRow", row)) for row in rows.tuples()]
