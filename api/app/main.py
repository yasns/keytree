import json
import logging
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import tsgauth.fastapi as tsgauth
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from .config import settings
from .db.base import engine
from .routers.health import router as health_router
from .routers.subsystems import router as subsystems_router
from .routers.user import router as user_router

log = logging.getLogger("access")

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(message)s"))
logging.basicConfig(level=settings.log_level, handlers=[_handler], force=True)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(
    title="Keytree",
    lifespan=lifespan,
    commit=settings.git_sha,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
tsgauth.setup_app(app, secret_key=settings.secret_key)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log.info(
        json.dumps(
            {
                "client": f"{request.client.host}:{request.client.port}"
                if request.client
                else None,
                "method": request.method,
                "path": request.url.path,
                "status": f"{response.status_code}",
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        )
    )
    return response


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/api/docs")


app.include_router(health_router, prefix="/api")
app.include_router(subsystems_router, prefix="/api")
app.include_router(user_router, prefix="/api")
