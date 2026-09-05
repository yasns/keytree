import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..config import settings
from ..db.base import SessionDep

log = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    """Process is up."""
    return {
        "status": "ok",
        "commit": settings.git_sha,
        "environment": settings.environment,
    }


@router.get("/ready")
async def ready(session: SessionDep) -> dict[str, str]:
    """Database is reachable and migrated."""
    try:
        await session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:
        # We don't want to leak any sensitive information to an unauthenticated client,
        # so log it instead.
        log.exception("readiness check failed")
        raise HTTPException(status_code=503, detail="database not ready") from None

    return {"status": "ok"}
