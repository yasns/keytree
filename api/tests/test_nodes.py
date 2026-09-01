from datetime import UTC, datetime

from app.db.models import Key, Mode, Node
from app.routers.nodes import _build_node_detail


def _key(id: int, mode_id: int, version: int) -> Key:
    return Key(
        id=id,
        mode_id=mode_id,
        node_id=42,
        version=version,
        label=f"ugt/rs_mp7/default/v{version}",
        staged_edit_id=id,
        created_by="keytree_app",
        comment="",
    )


def test_build_node_detail_versions_and_decommissioned_modes():
    node = Node(id=42, subsystem_id=3, name="rs_mp7", category="run_settings")

    active = Mode(id=118, node_id=42, name="default", description="Starter mode seed.")
    decommissioned = Mode(
        id=119,
        node_id=42,
        name="retired_line",
        description="Old line.",
        decommissioned_by="alice",
        decommissioned_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    keys = [_key(1, mode_id=118, version=1), _key(2, mode_id=118, version=2)]

    out = _build_node_detail(node, "ugt", [decommissioned, active], keys)

    assert out.id == 42
    assert out.category == "run_settings"
    assert out.subsystem_id == 3
    assert out.subsystem_name == "ugt"
    # sorted by mode id regardless of input order
    assert [m.name for m in out.modes] == ["default", "retired_line"]

    default_mode, retired_mode = out.modes
    assert default_mode.versions == [2, 1]  # newest first
    assert retired_mode.versions == []
    assert retired_mode.decommissioned_at == datetime(2026, 1, 1, tzinfo=UTC)
