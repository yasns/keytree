from fastapi import APIRouter, Depends, Request
from sqlalchemy.dialects.postgresql import insert
from tsgauth.fastapi import JWTBearerClaims

from app.authz import writable_subsystems
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


@router.get("/subsystems")
async def my_writable_subsystems(request: Request, session: SessionDep) -> list[str]:
    """Subsystem names the caller's roles grant write access to."""
    return sorted(await writable_subsystems(request.state.claims, session))


async def upsert_app_user(claims: dict[str, object], session: SessionDep) -> None:
    """Does not commit — caller must."""
    stmt = insert(AppUser).values(
        cern_login=claims["cern_upn"], display_name=claims["name"], email=claims.get("email")
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppUser.cern_login],
        set_={"display_name": stmt.excluded.display_name, "email": stmt.excluded.email},
    )
    _ = await session.execute(stmt)
