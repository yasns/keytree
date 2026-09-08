from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import Key, KeyChild, Mode, Node, Subsystem

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
    id: int
    alias: str
    label: str
    node_id: int
    node_name: str
    subsystem_name: str
    category: str | None
    """None for bundles."""
    payload: str | None
    """Only populated for external children."""
    mode_name: str
    version: int
    created_by: str
    created_at: datetime
    comment: str


async def key_or_404(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> Key:
    """Resolves a key by (subsystem, node, mode, version)."""
    key = await session.scalar(
        select(Key)
        .join(Mode, Mode.id == Key.mode_id)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .where(
            Subsystem.name == subsystem_name,
            Node.name == node_name,
            Mode.name == mode_name,
            Key.version == version,
        )
    )
    if key is None:
        raise HTTPException(status_code=404, detail="key not found")
    return key


@router.get("/{subsystem_name}/{node_name}/{mode_name}/{version}")
async def get_key(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> KeyOut:
    """Fetches a single key by (subsystem, node, mode, version)."""
    key = await key_or_404(subsystem_name, node_name, mode_name, version, session)
    return KeyOut.model_validate(key)


@router.get("/{subsystem_name}/{node_name}/{mode_name}/{version}/children")
async def get_key_children(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> list[KeyChildMetaOut]:
    """Returns one level of a bundle's key_child info. Crosses subsystem boundaries freely."""
    parent = await key_or_404(subsystem_name, node_name, mode_name, version, session)

    child = aliased(Key)

    rows = await session.execute(
        select(
            KeyChild.alias,
            child,
            Node.id,
            Node.name,
            Subsystem.name,
            Node.category,
            Mode.name,
        )
        .join(child, KeyChild.child_key_id == child.id)
        .join(Mode, Mode.id == child.mode_id)
        .join(Node, Node.id == Mode.node_id)
        .join(Subsystem, Subsystem.id == Node.subsystem_id)
        .where(KeyChild.parent_key_id == parent.id)
        .order_by(KeyChild.alias)
    )

    return [
        KeyChildMetaOut(
            id=child_key.id,
            alias=alias,
            label=child_key.label,
            node_id=child_node_id,
            node_name=child_node_name,
            subsystem_name=child_subsystem_name,
            category=child_category,
            payload=child_key.payload if child_category == "external" else None,
            mode_name=child_mode_name,
            version=child_key.version,
            created_by=child_key.created_by,
            created_at=child_key.created_at,
            comment=child_key.comment,
        )
        for (
            alias,
            child_key,
            child_node_id,
            child_node_name,
            child_subsystem_name,
            child_category,
            child_mode_name,
        ) in rows
    ]
