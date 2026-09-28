"""seed L1CE subsystems, namespaces, namespace edges

Revision ID: data_seed_legacy_catalog
Revises: data_base
Create Date: 2026-08-26 11:26:56.807619

"""

from collections.abc import Sequence
from typing import TypedDict

from alembic import op

from migrations.seed import namespace_ids_global, subsystem_ids, upsert

# revision identifiers, used by Alembic
revision: str = "data_seed_legacy_catalog"
down_revision: str | Sequence[str] | None = "data_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"


class _NamespaceSpecRequired(TypedDict):
    name: str


class NamespaceSpec(_NamespaceSpecRequired, total=False):
    category: str
    children: list[str]
    """Direct descendants of this subsystem bundled by this namespace."""
    leaves: list[str]
    """Payload namespaces owned by this one. Populated for bundles only."""


class SubsystemSpec(TypedDict):
    display_name: str
    category: str
    format: str | None
    namespaces: list[NamespaceSpec]


# leaf directly under root keeps its name; elsewhere the parent's name is prefixed
ROOT_VERTEX = "conf"

CATALOG: dict[str, SubsystemSpec] = {
    "l1_hlt": {
        "display_name": "L1 + HLT",
        "category": "top_level",
        "format": None,
        "namespaces": [
            NamespaceSpec(name="conf", category="external", leaves=["hlt_key", "hlt_sw_arch"]),
        ],
    },
    "cms_run": {
        "display_name": "CMS",
        "category": "top_level",
        "format": None,
        "namespaces": [
            NamespaceSpec(
                name="conf",
                category="external",
                leaves=[
                    "l1_hlt_mode",
                    "clock_source",
                    "pixel_run_key",
                    "tracker_run_key",
                    "es_run_key",
                    "ecal_run_key",
                    "hcal_run_key",
                    "hf_run_key",
                    "dt_run_key",
                    "csc_run_key",
                    "rpc_run_key",
                    "daq_run_key",
                    "dqm_run_key",
                    "trg_run_key",
                    "use_primary_tcds",
                    "tcds_run_key",
                ],
            ),
        ],
    },
    "l1_trg": {
        "display_name": "L1 Trigger",
        "category": "top_level",
        "format": None,
        "namespaces": [
            NamespaceSpec(name="conf", children=["tcds"]),
            NamespaceSpec(name="rs"),
            NamespaceSpec(name="tcds"),
        ],
    },
    "tcds": {
        "display_name": "TCDS",
        "category": "top_level",
        "format": "plaintext",
        "namespaces": [
            NamespaceSpec(name="conf", category="tcds", leaves=["pi", "ici"]),
        ],
    },
    "ugt": {
        "display_name": "uGT",
        "category": "subsystem",
        "format": "yaml",
        "namespaces": [
            NamespaceSpec(name="conf", children=["hw", "infra", "algo", "l1_menu"]),
            NamespaceSpec(
                name="rs",
                category="run_settings",
                leaves=[
                    "mp7",
                    "amc502_extcond",
                    "amc502_finor",
                    "algobx_mask",
                    "algo_finor_mask",
                    "algo_finor_veto",
                    "algo_prescale",
                ],
            ),
            NamespaceSpec(name="algo", category="algo"),
            NamespaceSpec(
                name="infra",
                category="infra",
                leaves=["mp7", "amc502_extcond", "amc502_finor"],
            ),
            NamespaceSpec(name="hw", category="hardware"),
            NamespaceSpec(name="l1_menu", category="l1_menu"),
        ],
    },
    "ugmt": {
        "display_name": "uGMT",
        "category": "subsystem",
        "format": "yaml",
        "namespaces": [
            NamespaceSpec(name="conf", children=["hw", "infra", "algo"]),
            NamespaceSpec(
                name="rs",
                category="run_settings",
                leaves=["mp7", "mp7_moni", "amc13_moni"],
            ),
            NamespaceSpec(name="algo", category="algo", leaves=["mp7", "luts"]),
            NamespaceSpec(
                name="infra",
                category="infra",
                leaves=["amc13", "readoutmenu", "techparams"],
            ),
            NamespaceSpec(name="hw", category="hardware"),
        ],
    },
    "calol1": {
        "display_name": "CaloL1",
        "category": "subsystem",
        "format": "yaml",
        "namespaces": [
            NamespaceSpec(name="conf", children=["hw", "infra", "algo"]),
            NamespaceSpec(
                name="rs",
                category="run_settings",
                leaves=["link_masks", "tower_masks", "monitor_settings", "tmt_cycle_config"],
            ),
            NamespaceSpec(name="algo", category="algo"),
            NamespaceSpec(name="infra", category="infra"),
            NamespaceSpec(name="hw", category="hardware"),
        ],
    },
    "calol2": {
        "display_name": "CaloL2",
        "category": "subsystem",
        "format": "yaml",
        "namespaces": [
            NamespaceSpec(name="conf", children=["hw", "infra", "algo"]),
            NamespaceSpec(
                name="rs",
                category="run_settings",
                leaves=["monitoring_and_masks", "tmt_redundancy_mode"],
            ),
            NamespaceSpec(
                name="algo",
                category="algo",
                leaves=["demux", "mps_common", "mps_jet", "mp_egamma", "mp_sum", "mp_tau"],
            ),
            NamespaceSpec(
                name="infra",
                category="infra",
                leaves=["amc13", "mp7", "mps", "demux"],
            ),
            NamespaceSpec(name="hw", category="hardware"),
        ],
    },
    "bmtf": {
        "display_name": "BMTF",
        "category": "subsystem",
        "format": "yaml",
        "namespaces": [
            NamespaceSpec(name="conf", children=["hw", "infra", "algo"]),
            NamespaceSpec(name="rs", category="run_settings", leaves=["amc13", "mp7"]),
            NamespaceSpec(name="algo", category="algo"),
            NamespaceSpec(name="infra", category="infra", leaves=["amc13", "mp7"]),
            NamespaceSpec(name="hw", category="hardware"),
        ],
    },
    "omtf": {
        "display_name": "OMTF",
        "category": "subsystem",
        "format": "yaml",
        "namespaces": [
            NamespaceSpec(name="conf", children=["hw", "infra", "algo"]),
            NamespaceSpec(name="rs", category="run_settings"),
            NamespaceSpec(name="algo", category="algo"),
            NamespaceSpec(name="infra", category="infra"),
            NamespaceSpec(name="hw", category="hardware"),
        ],
    },
    "emtf": {
        "display_name": "EMTF",
        "category": "subsystem",
        "format": "yaml",
        "namespaces": [
            NamespaceSpec(name="conf", children=["hw", "infra", "algo"]),
            NamespaceSpec(name="rs", category="run_settings"),
            NamespaceSpec(name="algo", category="algo"),
            NamespaceSpec(name="infra", category="infra", leaves=["amc13", "mtf7"]),
            NamespaceSpec(name="hw", category="hardware"),
        ],
    },
    "twinmux": {
        "display_name": "TwinMux",
        "category": "subsystem",
        "format": "yaml",
        "namespaces": [
            NamespaceSpec(name="conf", children=["hw", "infra", "algo"]),
            NamespaceSpec(name="rs", category="run_settings"),
            NamespaceSpec(name="algo", category="algo"),
            NamespaceSpec(
                name="infra",
                category="infra",
                leaves=[
                    "amc13",
                    "tm7_common",
                    "tm7_wheel_m2",
                    "tm7_wheel_m1",
                    "tm7_wheel_0",
                    "tm7_wheel_p1",
                    "tm7_wheel_p2",
                ],
            ),
            NamespaceSpec(name="hw", category="hardware"),
        ],
    },
    "spare_ugt": {
        "display_name": "Spare uGT",
        "category": "subsystem",
        "format": "yaml",
        "namespaces": [
            NamespaceSpec(name="conf", category="hardware", leaves=["hw"]),
        ],
    },
    "cppf": {
        "display_name": "CPPF",
        "category": "subsystem",
        "format": "xml",
        "namespaces": [
            NamespaceSpec(name="conf", children=["hw", "infra", "algo"]),
            NamespaceSpec(name="rs", category="run_settings"),
            NamespaceSpec(name="algo", category="algo"),
            NamespaceSpec(name="infra", category="infra"),
            NamespaceSpec(name="hw", category="hardware"),
        ],
    },
}

# (parent subsystem, namespace, child subsystem, namespace, alias); alias set where one parent
# needs several pointers to the same child namespace.
REFERENCES: list[tuple[str, str, str, str, str | None]] = [
    ("l1_hlt", "conf", "l1_trg", "conf", None),
    ("l1_hlt", "conf", "l1_trg", "rs", None),
    # tcds subsystems all draw from the one tcds/conf pool
    ("l1_trg", "tcds", "tcds", "conf", "ugt"),
    ("l1_trg", "tcds", "tcds", "conf", "ugmt"),
    ("l1_trg", "tcds", "tcds", "conf", "calol1"),
    ("l1_trg", "tcds", "tcds", "conf", "calol2"),
    ("l1_trg", "tcds", "tcds", "conf", "bmtf"),
    ("l1_trg", "tcds", "tcds", "conf", "emtf"),
    ("l1_trg", "tcds", "tcds", "conf", "omtf"),
    ("l1_trg", "tcds", "tcds", "conf", "twinmux"),
    ("l1_trg", "conf", "ugt", "conf", None),
    ("l1_trg", "conf", "ugmt", "conf", None),
    ("l1_trg", "conf", "calol1", "conf", None),
    ("l1_trg", "conf", "calol2", "conf", None),
    ("l1_trg", "conf", "bmtf", "conf", None),
    ("l1_trg", "conf", "emtf", "conf", None),
    ("l1_trg", "conf", "omtf", "conf", None),
    ("l1_trg", "conf", "twinmux", "conf", None),
    ("l1_trg", "conf", "cppf", "conf", None),
    ("l1_trg", "rs", "ugt", "rs", None),
    ("l1_trg", "rs", "ugmt", "rs", None),
    ("l1_trg", "rs", "calol1", "rs", None),
    ("l1_trg", "rs", "calol2", "rs", None),
    ("l1_trg", "rs", "bmtf", "rs", None),
    ("l1_trg", "rs", "emtf", "rs", None),
    ("l1_trg", "rs", "omtf", "rs", None),
    ("l1_trg", "rs", "twinmux", "rs", None),
    ("l1_trg", "rs", "cppf", "rs", None),
    # ugt/rs pointed at twice: alias distinguishes this one
    ("l1_trg", "rs", "ugt", "rs", "spare_ugt_rs"),
    ("spare_ugt", "conf", "ugt", "infra", None),
    ("spare_ugt", "conf", "ugt", "algo", None),
    ("spare_ugt", "conf", "ugt", "l1_menu", None),
]


def _leaf_name(parent: str, leaf: str) -> str:
    return leaf if parent == ROOT_VERTEX else f"{parent}_{leaf}"


def _subsystem_rows() -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "display_name": spec["display_name"],
            "category": spec["category"],
        }
        for name, spec in CATALOG.items()
    ]


def _namespace_rows(subsystem_ids: dict[str, int]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sub_name, spec in CATALOG.items():
        subsystem_id = subsystem_ids[sub_name]
        for namespace in spec["namespaces"]:
            leaves = namespace.get("leaves", [])
            # Category (and thus format) is reserved for leaves.
            category = None if leaves else namespace.get("category")
            rows.append(
                {
                    "subsystem_id": subsystem_id,
                    "name": namespace["name"],
                    "category": category,
                    "format": spec.get("format") if category is not None else None,
                }
            )
            rows.extend(
                {
                    "subsystem_id": subsystem_id,
                    "name": _leaf_name(namespace["name"], leaf),
                    "category": namespace.get("category"),
                    "format": spec.get("format"),
                }
                for leaf in leaves
            )
    return rows


def _edge_rows(namespace_ids: dict[tuple[str, str], int]) -> list[dict[str, object]]:
    edges: list[tuple[tuple[str, str], tuple[str, str], str]] = []
    for sub_name, spec in CATALOG.items():
        for namespace in spec["namespaces"]:
            parent = (sub_name, namespace["name"])
            # Within a subsystem the child's own name is unique already, so it is the alias.
            edges.extend(
                (parent, (sub_name, child), child) for child in namespace.get("children", [])
            )
            edges.extend(
                (parent, (sub_name, name), name)
                for name in (
                    _leaf_name(namespace["name"], leaf) for leaf in namespace.get("leaves", [])
                )
            )
    edges.extend(
        (
            (parent_sub, parent_namespace),
            (child_sub, child_namespace),
            alias or f"{child_sub}_{child_namespace}",
        )
        for parent_sub, parent_namespace, child_sub, child_namespace, alias in REFERENCES
    )
    # upsert() sends one INSERT, and Postgres refuses to resolve the same conflict twice.
    return [
        {
            "parent_namespace_id": namespace_ids[parent],
            "child_namespace_id": namespace_ids[child],
            "alias": alias,
        }
        for parent, child, alias in dict.fromkeys(edges)
    ]


def upgrade() -> None:
    bind = op.get_bind()
    upsert("subsystem", _subsystem_rows(), key=["name"])
    upsert("namespace", _namespace_rows(subsystem_ids(bind)), key=["subsystem_id", "name"])
    upsert(
        "namespace_edge",
        _edge_rows(namespace_ids_global(bind)),
        key=["parent_namespace_id", "child_namespace_id", "alias"],
    )


def downgrade() -> None:
    pass
