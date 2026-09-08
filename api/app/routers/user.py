from fastapi import APIRouter, Depends, Request
from sqlalchemy.dialects.postgresql import insert
from tsgauth.fastapi import JWTBearerClaims

from app.db.base import SessionDep
from app.db.models import AppUser

router = APIRouter(
    prefix="/user",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["user"],
)


@router.get("/claims")
def who_am_i(request: Request) -> dict[str, object]:
    """Returns the caller's JWT claims."""
    return request.state.claims


async def upsert_app_user(claims: dict[str, object], session: SessionDep) -> None:
    """Creates or refreshes an app_user row from JWT claims. Does not commit."""
    stmt = insert(AppUser).values(cern_login=claims["cern_upn"], display_name=claims["name"])
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppUser.cern_login], set_={"display_name": stmt.excluded.display_name}
    )
    _ = await session.execute(stmt)
