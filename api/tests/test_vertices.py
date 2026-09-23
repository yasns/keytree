from datetime import UTC, datetime

from app.db.models import Key, Mode, Vertex
from app.routers.vertices import _build_vertex_detail


def _key(id: int, mode_id: int, version: int) -> Key:
    return Key(
        id=id,
        mode_id=mode_id,
        vertex_id=42,
        version=version,
        label=f"ugt/rs_mp7/default/v{version}",
        staged_edit_id=id,
        created_by="keytree_app",
        comment="",
    )


def test_build_vertex_detail_versions_and_archived_modes():
    vertex = Vertex(id=42, subsystem_id=3, name="rs_mp7", category="run_settings", format="yaml")

    # ids deliberately reversed relative to name order, to prove sorting is by name
    active = Mode(
        id=119,
        vertex_id=42,
        name="default",
        description="Starter mode seed.",
        created_by="keytree_app",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    archived = Mode(
        id=118,
        vertex_id=42,
        name="retired_line",
        description="Old line.",
        created_by="keytree_app",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        archived_by="alice",
        archived_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    keys = [_key(1, mode_id=119, version=1), _key(2, mode_id=119, version=2)]

    display_names = {"keytree_app": "Keytree App", "alice": "Alice"}
    out = _build_vertex_detail(vertex, "ugt", [archived, active], keys, display_names)

    assert out.id == 42
    assert out.category == "run_settings"
    assert out.format == "yaml"
    assert out.subsystem_id == 3
    assert out.subsystem_name == "ugt"
    # sorted alphabetically by name, not by id or input order
    assert [m.name for m in out.modes] == ["default", "retired_line"]

    default_mode, retired_mode = out.modes
    assert default_mode.versions == [2, 1]  # newest first
    assert default_mode.created_by_display_name == "Keytree App"
    assert default_mode.archived_by_display_name is None
    assert retired_mode.versions == []
    assert retired_mode.archived_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert retired_mode.archived_by_display_name == "Alice"
