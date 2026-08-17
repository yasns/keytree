import json
import logging
import sys
import time

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from .config import APP_VERSION, settings
from .routers.users import router as users_router

log = logging.getLogger("access")

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(message)s"))
logging.basicConfig(level=settings.log_level, handlers=[_handler], force=True)

app = FastAPI(
    title="Keytree",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "commit": settings.git_sha,
        "environment": settings.environment,
    }


app.include_router(users_router)
