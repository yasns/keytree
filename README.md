# Keytree
**_The CMS L1T+HLT configuration database editor for the Phase-2 upgrade._**
Built on PostgreSQL, FastAPI, and Vue 3.

## Run locally

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ENVIRONMENT=local GIT_SHA=$(git rev-parse --short HEAD) \
  uvicorn app.main:app --reload --port 8080
```

```bash
cd web
npm install
npm run dev
```

Then: <http://localhost:5173/> for the app, <http://localhost:5173/api/docs> for the Swagger API docs. Vite proxies `/api` to the API on port 8080 (single origin).

## Build and run the containers

```bash
docker build \
  -f api/Dockerfile \
  --build-arg APP_VERSION=$(grep -m1 '^version' api/pyproject.toml | sed -E 's/version = "(.*)"/\1/') \
  --build-arg GIT_SHA=$(git rev-parse --short HEAD) \
  -t keytree-api .

docker network create keytree

docker run -d --rm --network keytree --name api -e ENVIRONMENT=local keytree-api
```

```bash
docker build -f web/Dockerfile . -t keytree-web

docker run -d --rm --network keytree -p 8081:8080 keytree-web
```

Then: <http://localhost:8081/>. nginx proxies `/api/` to the api container by
its Docker network hostname (`api:8080`).
