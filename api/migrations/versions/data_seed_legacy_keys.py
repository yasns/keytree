"""seed legacy authors and per-subsystem modes/keys

Revision ID: data_seed_legacy_keys
Revises: data_seed_shepherd_demo
Create Date: 2026-09-28 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import column, select, table, text

from migrations.seed import (
    insert_changeset,
    insert_key,
    insert_mode,
    load_fixture,
    namespace_ids_global,
    upsert,
)

# revision identifiers, used by Alembic
revision: str = "data_seed_legacy_keys"
down_revision: str | Sequence[str] | None = "data_seed_shepherd_demo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"

MODE_T = table("mode", column("id"), column("name"), column("namespace_id"))
KEY_T = table("key", column("id"), column("mode_id"), column("namespace_id"), column("version"))

# subsystems that follow the standard import -> archive conf/rs -> demo-bundle pattern;
# archive_ns is which of "conf"/"rs" to archive, demo is add_demo_bundle_key's children arg
SUBSYSTEMS: dict[str, dict] = {
    "ugt": {
        "archive_ns": ("conf", "rs"),
        "demo": [
            ("hw", "ugt", "hw"),
            ("infra", "ugt", "infra"),
            ("algo", "ugt", "algo"),
            ("l1_menu", "ugt", "l1_menu"),
        ],
    },
    "ugmt": {
        "archive_ns": ("conf", "rs"),
        "demo": [("hw", "ugmt", "hw"), ("infra", "ugmt", "infra"), ("algo", "ugmt", "algo")],
    },
    "calol1": {
        "archive_ns": ("conf", "rs"),
        "demo": [("hw", "calol1", "hw"), ("infra", "calol1", "infra"), ("algo", "calol1", "algo")],
    },
    "calol2": {
        "archive_ns": ("conf", "rs"),
        "demo": [("hw", "calol2", "hw"), ("infra", "calol2", "infra"), ("algo", "calol2", "algo")],
    },
    "bmtf": {
        "archive_ns": ("conf", "rs"),
        "demo": [("hw", "bmtf", "hw"), ("infra", "bmtf", "infra"), ("algo", "bmtf", "algo")],
    },
    "emtf": {
        "archive_ns": (),
        "demo": [("hw", "emtf", "hw"), ("infra", "emtf", "infra"), ("algo", "emtf", "algo")],
    },
    "omtf": {
        "archive_ns": (),
        "demo": [("hw", "omtf", "hw"), ("infra", "omtf", "infra"), ("algo", "omtf", "algo")],
    },
    "twinmux": {
        "archive_ns": ("conf",),
        "demo": [
            ("hw", "twinmux", "hw"),
            ("infra", "twinmux", "infra"),
            ("algo", "twinmux", "algo"),
        ],
    },
    "spare_ugt": {
        "archive_ns": ("conf",),
        "demo": [
            ("hw", "spare_ugt", "hw"),
            ("ugt_infra", "ugt", "infra"),
            ("ugt_algo", "ugt", "algo"),
            ("ugt_l1_menu", "ugt", "l1_menu"),
        ],
    },
}


def by_namespace(rows: list[list], namespace: str) -> list[tuple]:
    """Filter (namespace, *rest) fixture rows to `namespace`, dropping the leading tag."""
    return [tuple(row[1:]) for row in rows if row[0] == namespace]


def archive_mode(bind, *, changeset_id: int, mode_id: int, archived_by: str, archived_at) -> None:
    """Retire an entire mode -- mirrors insert_key's staged_edit + key pattern."""
    bind.execute(
        text("""
            INSERT INTO staged_archival (changeset_id, mode_id, archived)
            VALUES (:changeset_id, :mode_id, true)
        """),
        {"changeset_id": changeset_id, "mode_id": mode_id},
    )
    bind.execute(
        text("UPDATE mode SET archived_by = :who, archived_at = :when WHERE id = :mode_id"),
        {"who": archived_by, "when": archived_at, "mode_id": mode_id},
    )


def decommission_key(
    bind, *, changeset_id: int, key_id: int, decommissioned_by: str, decommissioned_at
) -> None:
    """Retire a single key version -- mirrors insert_key's staged_edit + key pattern."""
    bind.execute(
        text("""
            INSERT INTO staged_decommission (changeset_id, key_id, decommissioned)
            VALUES (:changeset_id, :key_id, true)
        """),
        {"changeset_id": changeset_id, "key_id": key_id},
    )
    bind.execute(
        text(
            "UPDATE key SET decommissioned_by = :who, decommissioned_at = :when WHERE id = :key_id"
        ),
        {"who": decommissioned_by, "when": decommissioned_at, "key_id": key_id},
    )


def archive_modes(
    bind, subsystem: str, namespace: str, modes: list[tuple[str, object]], changeset_id: int
) -> None:
    """Archive whole modes after the fact -- `modes` is (mode_name, archived_at)."""
    ns_ids = namespace_ids_global(bind)
    namespace_id = ns_ids[(subsystem, namespace)]
    mode_ids = {
        name: mode_id
        for name, mode_id in bind.execute(
            select(MODE_T.c.name, MODE_T.c.id).where(MODE_T.c.namespace_id == namespace_id)
        )
    }
    for name, archived_at in modes:
        archive_mode(
            bind,
            changeset_id=changeset_id,
            mode_id=mode_ids[name],
            archived_by="keytree_app",
            archived_at=archived_at,
        )


def decommission_keys(
    bind, subsystem: str, namespace: str, keys: list[tuple[str, int, object]], changeset_id: int
) -> None:
    """Decommission specific key versions -- `keys` is (mode_name, version, decommissioned_at)."""
    ns_ids = namespace_ids_global(bind)
    namespace_id = ns_ids[(subsystem, namespace)]
    for mode_name, version, decommissioned_at in keys:
        key_id = bind.execute(
            select(KEY_T.c.id)
            .select_from(KEY_T.join(MODE_T, KEY_T.c.mode_id == MODE_T.c.id))
            .where(
                MODE_T.c.namespace_id == namespace_id,
                MODE_T.c.name == mode_name,
                KEY_T.c.version == version,
            )
        ).scalar()
        decommission_key(
            bind,
            changeset_id=changeset_id,
            key_id=key_id,
            decommissioned_by="keytree_app",
            decommissioned_at=decommissioned_at,
        )


def insert_key_child(
    bind,
    *,
    parent_key_id: int,
    alias: str,
    child_key_id: int,
    parent_namespace_id: int,
    child_namespace_id: int,
) -> None:
    bind.execute(
        text("""
            INSERT INTO key_child
                (parent_key_id, alias, child_key_id, parent_namespace_id, child_namespace_id)
            VALUES
                (:parent_key_id, :alias, :child_key_id, :parent_namespace_id, :child_namespace_id)
        """),
        {
            "parent_key_id": parent_key_id,
            "alias": alias,
            "child_key_id": child_key_id,
            "parent_namespace_id": parent_namespace_id,
            "child_namespace_id": child_namespace_id,
        },
    )


def key_id_by_version(bind, namespace_id: int, mode: str, version: int) -> int | None:
    return bind.execute(
        select(KEY_T.c.id)
        .select_from(KEY_T.join(MODE_T, KEY_T.c.mode_id == MODE_T.c.id))
        .where(
            MODE_T.c.namespace_id == namespace_id,
            MODE_T.c.name == mode,
            KEY_T.c.version == version,
        )
    ).scalar()


def insert_bundle_key(
    bind,
    *,
    changeset_id: int,
    mode_id: int,
    namespace_id: int,
    version: int,
    label: str,
    created_by: str,
    comment: str,
    children: dict[str, tuple[int, int]],
    created_at=None,
    validation_status: str = "skipped",
) -> int:
    """insert_key with `children` (alias -> (key_id, namespace_id)), then wire key_child rows."""
    key_id = insert_key(
        bind,
        changeset_id=changeset_id,
        mode_id=mode_id,
        namespace_id=namespace_id,
        version=version,
        label=label,
        created_by=created_by,
        created_at=created_at,
        comment=comment,
        children={alias: child_key_id for alias, (child_key_id, _) in children.items()},
        validation_status=validation_status,
    )
    for alias, (child_key_id, child_namespace_id) in children.items():
        insert_key_child(
            bind,
            parent_key_id=key_id,
            alias=alias,
            child_key_id=child_key_id,
            parent_namespace_id=namespace_id,
            child_namespace_id=child_namespace_id,
        )
    return key_id


def import_legacy(bind, subsystem: str, modes: list[dict], keys: list[dict]) -> int:
    """Each key entry has either "payload" (leaf) or "children" (bundle), never both.

    A child ref is (namespace, mode, version) for a same-subsystem child, or
    (subsystem, namespace, mode, version) for one in another subsystem. Children are
    resolved by live DB lookup, not an in-memory map, since they may come from an
    earlier migration or an earlier namespace in this same one; a ref that doesn't
    resolve is silently dropped from the bundle.
    """
    ns_ids = namespace_ids_global(bind)
    namespace_ids = {ns: ns_id for (sub, ns), ns_id in ns_ids.items() if sub == subsystem}

    for m in modes:
        insert_mode(
            bind,
            namespace_ids[m["namespace"]],
            m["name"],
            m["description"],
            m["created_by"],
            m["created_at"],
        )

    mode_ids = {
        (namespace_id, name): mode_id
        for namespace_id, name, mode_id in bind.execute(
            select(MODE_T.c.namespace_id, MODE_T.c.name, MODE_T.c.id).where(
                MODE_T.c.namespace_id.in_(namespace_ids.values())
            )
        )
    }

    changeset_id = insert_changeset(bind, "keytree_app", [f"keytree_{subsystem}_expert"])

    # bundles may reference any leaf key regardless of relative order in `keys`
    leaf_keys = [k for k in keys if k["children"] is None]
    bundle_keys = [k for k in keys if k["children"] is not None]

    for k in leaf_keys:
        namespace_id = namespace_ids[k["namespace"]]
        mode_id = mode_ids[(namespace_id, k["mode"])]
        label = f"{subsystem}/{k['namespace']}/{k['mode']}/v{k['version']}"
        insert_key(
            bind,
            changeset_id=changeset_id,
            mode_id=mode_id,
            namespace_id=namespace_id,
            version=k["version"],
            label=label,
            created_by=k["created_by"],
            created_at=k["created_at"],
            comment=k["comment"],
            payload=k["payload"] if k["payload"] is not None else "",
            validation_status=k.get("validation_status", "skipped"),
        )

    for k in bundle_keys:
        namespace_id = namespace_ids[k["namespace"]]
        mode_id = mode_ids[(namespace_id, k["mode"])]
        label = f"{subsystem}/{k['namespace']}/{k['mode']}/v{k['version']}"

        children = {}
        for alias, ref in k["children"].items():
            c_sub, c_ns, c_mode, c_version = ref if len(ref) == 4 else (subsystem, *ref)
            child_namespace_id = ns_ids[(c_sub, c_ns)]
            child_key_id = key_id_by_version(bind, child_namespace_id, c_mode, c_version)
            if child_key_id is not None:
                children[alias] = (child_key_id, child_namespace_id)

        insert_bundle_key(
            bind,
            changeset_id=changeset_id,
            mode_id=mode_id,
            namespace_id=namespace_id,
            version=k["version"],
            label=label,
            created_by=k["created_by"],
            created_at=k["created_at"],
            comment=k["comment"],
            children=children,
            validation_status=k.get("validation_status", "skipped"),
        )

    return changeset_id


def add_demo_bundle_key(
    bind, subsystem: str, namespace: str, children: list[tuple[str, str, str]]
) -> None:
    """A child with no shepherd_demo key (non-yaml format) is silently skipped for that alias."""
    ns_ids = namespace_ids_global(bind)
    namespace_id = ns_ids[(subsystem, namespace)]

    resolved: dict[str, tuple[int, int]] = {}
    for alias, child_subsystem, child_namespace in children:
        child_namespace_id = ns_ids.get((child_subsystem, child_namespace))
        if child_namespace_id is None:
            continue
        child_key_id = key_id_by_version(bind, child_namespace_id, "shepherd_demo", 2)
        if child_key_id is not None:
            resolved[alias] = (child_key_id, child_namespace_id)

    comment = "Demo bundle wired to ShepHerd fixture children"
    mode_id = insert_mode(bind, namespace_id, "shepherd_demo", comment, "keytree_app")
    changeset_id = insert_changeset(bind, "keytree_app", ["keytree_superuser"])
    label = f"{subsystem}/{namespace}/shepherd_demo/v1"
    insert_bundle_key(
        bind,
        changeset_id=changeset_id,
        mode_id=mode_id,
        namespace_id=namespace_id,
        version=1,
        label=label,
        created_by="keytree_app",
        comment=comment,
        children=resolved,
        validation_status="passed",
    )


def _seed_external_leaves(bind) -> None:
    ns_ids = namespace_ids_global(bind)

    for leaf in load_fixture("legacy_external")["leaves"]:
        subsystem, leaf_ns, entries = leaf["subsystem"], leaf["leaf_ns"], leaf["entries"]
        namespace_id = ns_ids[(subsystem, leaf_ns)]
        mode_id = bind.execute(
            select(MODE_T.c.id).where(
                MODE_T.c.namespace_id == namespace_id, MODE_T.c.name == "default"
            )
        ).scalar()

        next_version = bind.execute(
            select(KEY_T.c.version)
            .where(KEY_T.c.mode_id == mode_id)
            .order_by(KEY_T.c.version.desc())
            .limit(1)
        ).scalar()
        next_version = (next_version or 0) + 1

        changeset_id = insert_changeset(bind, "keytree_app", ["keytree_superuser"])

        decommissioned = []
        for entry in entries:
            version = next_version
            next_version += 1
            label = f"{subsystem}/{leaf_ns}/default/v{version}"

            insert_key(
                bind,
                changeset_id=changeset_id,
                mode_id=mode_id,
                namespace_id=namespace_id,
                version=version,
                label=label,
                created_by=entry["created_by"],
                created_at=entry["created_at"],
                comment=entry["comment"],
                payload=entry["value"],
                validation_status="skipped",
            )
            if entry["failed"]:
                decommissioned.append(("default", version, entry["created_at"]))

        if decommissioned:
            decommission_keys(bind, subsystem, leaf_ns, decommissioned, changeset_id)


def upgrade() -> None:
    bind = op.get_bind()

    upsert(
        "app_user",
        [
            {"cern_login": login, "display_name": name}
            for login, name in load_fixture("legacy_authors").items()
        ],
        key=["cern_login"],
    )

    fx = load_fixture("legacy_tcds")
    changeset_id = import_legacy(bind, "tcds", fx["modes"], fx["keys"])
    decommission_keys(
        bind, "tcds", "ici", by_namespace(fx["decommissioned_keys"], "ici"), changeset_id
    )

    fx = load_fixture("legacy_cppf")
    import_legacy(bind, "cppf", fx["modes"], fx["keys"])

    for name, cfg in SUBSYSTEMS.items():
        fx = load_fixture(f"legacy_{name}")
        changeset_id = import_legacy(bind, name, fx["modes"], fx["keys"])
        for ns in cfg["archive_ns"]:
            archive_modes(bind, name, ns, by_namespace(fx["archived_modes"], ns), changeset_id)
        add_demo_bundle_key(bind, name, "conf", cfg["demo"])

    _seed_external_leaves(bind)

    fx = load_fixture("legacy_cms_run")
    changeset_id = import_legacy(bind, "cms_run", fx["modes"], fx["keys"])
    archive_modes(bind, "cms_run", "conf", by_namespace(fx["archived_modes"], "conf"), changeset_id)
    decommission_keys(
        bind, "cms_run", "conf", by_namespace(fx["decommissioned_keys"], "conf"), changeset_id
    )

    fx = load_fixture("legacy_l1_trg")
    for ns in ("tcds", "conf", "rs"):
        leaf = fx[ns]
        changeset_id = import_legacy(bind, "l1_trg", leaf["modes"], leaf["keys"])
        archive_modes(bind, "l1_trg", ns, by_namespace(leaf["archived_modes"], ns), changeset_id)

    fx = load_fixture("legacy_l1_hlt")
    changeset_id = import_legacy(bind, "l1_hlt", fx["modes"], fx["keys"])
    archive_modes(bind, "l1_hlt", "conf", by_namespace(fx["archived_modes"], "conf"), changeset_id)


def downgrade() -> None:
    pass
