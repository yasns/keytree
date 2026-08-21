# Keytree
**The CMS L1T+HLT configuration database editor for the Phase-2 upgrade.** Built on PostgreSQL, FastAPI, and Vue 3.

## Local setup

> Requires [uv](https://docs.astral.sh/uv/getting-started/installation/), Node, and Docker.

Run the database server first:
```bash
docker compose up -d db
```

Then set up the API:
```bash
cd api
uv sync
cp .env.example .env  # fill in the required environment variables
```

Connect as the owner, create the app privilege bundle:
```bash
docker compose exec db psql -U keytree -d keytree -c "CREATE ROLE keytree_app NOLOGIN"
```

Then create the API's login, assigning it the app role:
```bash
docker compose exec db psql -U keytree -d keytree \
  -c "CREATE USER keytree_api PASSWORD '...' IN ROLE keytree_app"
```

Run the migrations:
```bash
POSTGRES_USER=keytree POSTGRES_PASSWORD=keytree uv run alembic upgrade heads
```

The API connects as `keytree_api`, which only holds lowest-privilege grants (e.g., can't edit the key hierarchy). The role is needed again after any `docker compose down -v`.

Install the frontend dependencies for editor tooling:
```bash
cd web
npm install
```

### Run the whole stack
```bash
docker compose up
```
Then: <http://localhost:5173/> for the app, <http://localhost:5173/api/docs> for the Swagger API docs.

## Tests
The database fixtures use an ephemeral `postgres` via testcontainers.

```bash
cd api && uv run pytest tests
```

```bash
cd web && npm run test:unit
```

## Database

There are two independent migration branches:
1. `schema` defines the data structure and the grants. 
2. `tree` defines key hierarchy data as new subsystems are added.

The idea was to store the key hierarchy as data, not tables - makes it more dynamic. This is because as of writing this README, the exact key hierarchy is not known. Note that `tree` depends on `schema`, so data should never apply before the tables it needs. Here are some examples:

```bash
uv run alembic revision -m "add key table"      --head=schema@head  # schema definition
uv run alembic revision -m "seed cms root keys" --head=tree@head    # key hierarchy only
uv run alembic upgrade heads                                        # apply both
uv run alembic heads                                                # where the branches end
uv run alembic downgrade schema@-1                                  # one branch only
```

The branches are otherwise unordered, so a tree revision that seeds a table must declare `depends_on` against the schema revision that creates it, if need be. Nothing else enforces that order.

### Grants

Every revision that creates a table grants its own privileges. A table whose revision forgets its grants is invisible to the API.

`keytree_app` is a `NOLOGIN` privilege bundle (role). Column-level grants should be assigned to it, to enable read/write access for the API, for example:
```sql
GRANT SELECT ON key TO keytree_app;                  -- read-only
GRANT UPDATE (display_name) ON key TO keytree_app;   -- if its mutable
```

### Seeding

Rows for tables the API cannot write (e.g. `KEY`) are typed `TypedDict` literals declared in the revision.

```python
from typing import TypedDict

from migrations.seed import seed


class KeyRow(TypedDict):
    path: str
    display_name: str
    category: str


ROOT_KEYS: list[KeyRow] = [
    {"path": "cms", "display_name": "CMS", "category": "base"},
]


def upgrade() -> None:
    seed("key", ROOT_KEYS, key=["path"])
```

`seed()` inserts or updates existing rows and does not import the app's ORM models as not to break migrations.

## Deployment

`POSTGRES_*` are environment-scoped CI variables, holding the `keytree_owner` credentials that `migrate-api` connects as. The running API connects separately, as `keytree_api`, via its own `POSTGRES_*` variables in the OKD secret.

Run these once per instance manually as the cluster admin:

```sql
CREATE DATABASE keytree;
CREATE USER keytree_owner PASSWORD '...';                   -- database owner for running migrations
GRANT keytree_owner TO admin;                               -- admin needs the role to hand ownership over
ALTER DATABASE keytree OWNER TO keytree_owner;
REVOKE keytree_owner FROM admin;                            -- optional cleanup
GRANT ALL ON SCHEMA public TO keytree_owner;                -- the owner can create tables, etc.
CREATE ROLE keytree_app NOLOGIN;                            -- the privilege bundle migrations grant to
CREATE USER keytree_api PASSWORD '...' IN ROLE keytree_app; -- API's user, lowest-privilege
```
