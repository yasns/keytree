from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import Key, Mode, Node, Subsystem

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
    created_by: str
    created_at: datetime
    comment: str

    model_config = {"from_attributes": True}


@router.get("/{subsystem_name}/{node_name}/{mode_name}/{version}")
async def get_key(
    subsystem_name: str, node_name: str, mode_name: str, version: int, session: SessionDep
) -> KeyOut:
    """Resolves a key by (subsystem, node, mode, version) locator."""
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
    return KeyOut.model_validate(key)
