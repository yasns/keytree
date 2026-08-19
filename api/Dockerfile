FROM registry.cern.ch/docker.io/astral/uv:0.12.5 AS uv

FROM registry.cern.ch/docker.io/library/python:3.11-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /src
ENV UV_PROJECT_ENVIRONMENT=/usr/local
COPY api/pyproject.toml api/uv.lock ./
COPY api/app ./app
RUN uv sync --locked --no-dev --no-editable

FROM registry.cern.ch/docker.io/library/python:3.11-slim

ARG GIT_SHA=unknown

COPY --from=builder /usr/local /usr/local

ENV GIT_SHA=${GIT_SHA} \
    HOME=/tmp \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chgrp -R 0 /usr/local && chmod -R g=u /usr/local

USER 1001
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--forwarded-allow-ips=*"]
