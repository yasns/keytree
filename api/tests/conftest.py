import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import NullPool, create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

# settings are read at import time, so the environment must exist first
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("GIT_SHA", "testsha")
os.environ.setdefault("SECRET_KEY", "test-secret")

API_DIR = Path(__file__).resolve().parent.parent
APP_USER = "app_role_test"
APP_PASSWORD = "app-role-test"
# CI overrides to the CERN mirror
POSTGRES_IMAGE = os.environ.get("POSTGRES_IMAGE", "postgres:17")


@pytest.fixture(scope="session")
def alembic_config():
    return Config(str(API_DIR / "alembic.ini"))


@pytest.fixture(scope="session")
def postgres(alembic_config):
    """
    Ephemeral postgres:17 migrated with `alembic upgrade heads` to preserve grants.
    """
    # PostgresContainer otherwise reads POSTGRES_* that app/__init__.py loaded from .env
    with PostgresContainer(
        POSTGRES_IMAGE,
        username="keytree",
        password="keytree",
        dbname="keytree",
        driver="psycopg",
    ) as container:
        url = container.get_connection_url()
        with create_engine(url).begin() as conn:
            conn.execute(text("CREATE ROLE keytree_app NOLOGIN"))
        alembic_config.set_main_option("sqlalchemy.url", url)
        command.upgrade(alembic_config, "heads")
        yield container


@pytest.fixture(scope="session")
def engine(postgres):
    """Synchronous, connected as the owner (to enable migrations)."""
    engine = create_engine(postgres.get_connection_url())
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(postgres, engine):
    """Connected as the app role and only having grants the API needs to run."""
    with engine.begin() as conn:
        conn.execute(text(f"CREATE USER {APP_USER} PASSWORD '{APP_PASSWORD}' IN ROLE keytree_app"))
    url = postgres.get_connection_url().replace(
        f"{postgres.username}:{postgres.password}@", f"{APP_USER}:{APP_PASSWORD}@"
    )
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def client(app_engine):
    """TestClient bound to the container as the app role the API runs as."""
    # ruff would otherwise hoist these imports above the os.environ block they depend on
    from fastapi.testclient import TestClient

    from app.db.base import get_session
    from app.main import app

    # NullPool: connections must not outlive the loop TestClient runs them on
    async_engine = create_async_engine(app_engine.url, poolclass=NullPool)
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

    async def override():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
