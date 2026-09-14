from datetime import UTC, datetime

from app.db.models import Key
from app.routers.keys import _build_child_meta, _build_key_detail


def _key() -> Key:
    return Key(
        id=9,
        mode_id=3,
        node_id=42,
        version=2,
        label="ugt/l1_menu/default/v2",
        payload="menu contents",
        staged_edit_id=1,
        created_by="jdoe",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        comment="new menu",
    )


def test_build_child_meta_fills_key_fields():
    meta = _build_child_meta(("l1_menu", _key(), 42, "l1_menu", "ugt", "menu", "default"))

    assert meta.id == 9
    assert meta.label == "ugt/l1_menu/default/v2"
    assert meta.mode_name == "default"
    assert meta.version == 2
    assert meta.created_by == "jdoe"
    # Payload is only carried for external children
    assert meta.payload is None


def test_build_child_meta_carries_external_payload():
    meta = _build_child_meta(("clock", _key(), 7, "clock_source", "cms_run", "external", "default"))

    assert meta.payload == "menu contents"


def test_build_child_meta_lists_empty_alias_with_null_key():
    meta = _build_child_meta(("l1_menu", None, 42, "l1_menu", "ugt", "menu", None))

    assert meta.alias == "l1_menu"
    # structural fields come off the edge: row still renders/refills
    assert meta.node_id == 42
    assert meta.node_name == "l1_menu"
    assert meta.subsystem_name == "ugt"
    assert meta.category == "menu"
    # Everything off the child key is absent
    assert meta.id is None
    assert meta.label is None
    assert meta.mode_name is None
    assert meta.version is None
    assert meta.created_by is None
    assert meta.created_at is None
    assert meta.comment is None
    assert meta.payload is None


def test_build_key_detail_fills_display_name_and_ancestor():
    out = _build_key_detail(_key(), "Jane Doe", "default", 3, "ugt/l1_menu/default/v3")

    assert out.created_by_display_name == "Jane Doe"
    assert out.based_on is not None
    assert out.based_on.mode_name == "default"
    assert out.based_on.version == 3
    assert out.based_on.label == "ugt/l1_menu/default/v3"


def test_build_key_detail_has_no_ancestor_without_fork_source_or_prior_version():
    out = _build_key_detail(_key(), "Jane Doe", None, None, None)

    assert out.based_on is None
