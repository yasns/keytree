from fastapi import APIRouter, Depends, Request
from tsgauth.fastapi import JWTBearerClaims

router = APIRouter(
    prefix="/user",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["user"],
)


@router.get("/claims")
def who_am_i(request: Request) -> dict[str, object]:
    """Returns the caller's JWT claims."""
    return request.state.claims
