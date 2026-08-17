from fastapi import APIRouter, Depends, Request
from tsgauth.fastapi import JWTBearerClaims

router = APIRouter(
    prefix="/api/user",
    dependencies=[Depends(JWTBearerClaims())],
    tags=["Users"],
)


@router.get("/claims")
def who_am_i(request: Request):
    return {"claims": request.state.claims}
