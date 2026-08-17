FROM registry.cern.ch/docker.io/library/python:3.11-slim AS builder

WORKDIR /src
COPY api/pyproject.toml ./
COPY api/app ./app
RUN pip install --no-cache-dir --prefix=/install .

FROM registry.cern.ch/docker.io/library/python:3.11-slim

ARG APP_VERSION=0.0.0
ARG GIT_SHA=unknown

COPY --from=builder /install /usr/local

ENV GIT_SHA=${GIT_SHA} \
    APP_VERSION=${APP_VERSION} \
    HOME=/tmp \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chgrp -R 0 /usr/local && chmod -R g=u /usr/local

USER 1001
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
