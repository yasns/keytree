"""Smoke tests for the database migrations."""

from typing import Any, TypedDict

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

import migrations.seed as seed_module


class ProbeRow(TypedDict):
    path: str
    display_name: str
    meta: dict[str, Any] | None


def test_both_branches_applied(engine, alembic_config):
    script = ScriptDirectory.from_config(alembic_config)
    with engine.connect() as conn:
        stored = set(conn.scalars(text("SELECT version_num FROM alembic_version")))
    # alembic stores one row per revision not subsumed by another via depends_on
    assert stored == set(script.get_heads())


def test_schema_branch_effects(engine):
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT true FROM pg_extension WHERE extname = 'ltree'"))
        assert conn.scalar(
            text("SELECT NOT rolcanlogin FROM pg_roles WHERE rolname = 'keytree_app'")
        ), "keytree_app must be a privilege bundle, not a login"


def test_ready_reports_the_applied_revision(client, engine):
    with engine.connect() as conn:
        stored = sorted(conn.scalars(text("SELECT version_num FROM alembic_version")))
    body = client.get("/api/health/ready").json()
    assert body["status"] == "ok"
    assert body["ltree"] is True
    assert sorted(body["applied_revisions"]) == stored
    assert body["server_version"].startswith("17.")


def test_seed_inserts_then_upserts(engine, monkeypatch):
    rows: list[ProbeRow] = [
        {"path": "cms", "display_name": "CMS", "meta": {"kind": "root"}},
        {"path": "cms.l1_hlt", "display_name": "L1 + HLT", "meta": None},
    ]
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE probe (id serial PRIMARY KEY, path ltree UNIQUE, "
                "display_name text, meta jsonb)"
            )
        )
        monkeypatch.setattr(seed_module.op, "get_bind", lambda: conn)

        seed_module.seed("probe", rows, key=["path"])
        assert conn.execute(text("SELECT count(*) FROM probe")).scalar() == 2

        seed_module.seed("probe", rows, key=["path"])  # idempotent
        assert conn.execute(text("SELECT count(*) FROM probe")).scalar() == 2

        renamed: list[ProbeRow] = [{"path": "cms", "display_name": "RENAMED", "meta": None}]
        seed_module.seed("probe", renamed, key=["path"])
        assert conn.execute(text("SELECT count(*) FROM probe")).scalar() == 2
        assert (
            conn.execute(text("SELECT display_name FROM probe WHERE path = 'cms'")).scalar()
            == "RENAMED"
        )

        # round-tripped as a real ltree, not text
        assert conn.execute(text("SELECT count(*) FROM probe WHERE path <@ 'cms'")).scalar() == 2
        conn.execute(text("DROP TABLE probe"))


def test_app_role_reads_but_cannot_write(app_engine):
    with app_engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version"))
    for statement in (
        "CREATE TABLE nope (id int)",
        "INSERT INTO alembic_version VALUES ('x')",
    ):
        with app_engine.connect() as conn:
            with pytest.raises(ProgrammingError, match="permission denied"):
                conn.execute(text(statement))
