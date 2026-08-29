"""seed legacy subsystems, nodes, node edges

Revision ID: data_legacy_catalog
Revises: data_base
Create Date: 2026-08-26 11:26:56.807619

"""

from collections.abc import Sequence
from typing import TypedDict

from alembic import op
from sqlalchemy import column, select, table

from migrations.seed import seed

# revision identifiers, used by Alembic
revision: str = "data_legacy_catalog"
down_revision: str | Sequence[str] | None = "data_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"


class _NodeSpecRequired(TypedDict):
    name: str


class NodeSpec(_NodeSpecRequired, total=False):
    category: str
    format: str
    children: list[str]
    """Sibling nodes of the same subsystem, which this node bundles."""
    leaves: list[str]
    """Payload nodes owned by this one. If specified, this node becomes a container.
    """


class SubsystemSpec(TypedDict):
    display_name: str
    category: str
    description: str
    nodes: list[NodeSpec]


# The root node for a subsystem key.
# A leaf directly under it keeps its original name. Anywhere else the parent's name is prefixed.
ROOT_NODE = "conf"

CATALOG: dict[str, SubsystemSpec] = {
    "l1_hlt": {
        "display_name": "L1 + HLT",
        "category": "top_level",
        "description": "Combined L1 Trigger + HLT run point.",
        "nodes": [
            NodeSpec(name="conf", format="plaintext", leaves=["hlt_key", "hlt_sw_arch"]),
        ],
    },
    "cms_run": {
        "display_name": "CMS",
        "category": "top_level",
        "description": "Top-level CMS run configuration, aggregated from every detector.",
        "nodes": [
            NodeSpec(
                name="conf",
                format="plaintext",
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
        "description": "Aggregates config and run settings from all L1 trigger subsystems.",
        "nodes": [
            NodeSpec(name="conf", children=["tcds"]),
            NodeSpec(name="rs"),
            NodeSpec(name="tcds"),
        ],
    },
    "tcds": {
        "display_name": "TCDS",
        "category": "top_level",
        "description": "Distributes the clock and L1 accept signal to every subsystem.",
        "nodes": [
            NodeSpec(name="conf", category="tcds", format="xml", leaves=["pi", "ici"]),
        ],
    },
    "ugt": {
        "display_name": "uGT",
        "category": "subsystem",
        "description": "Global Trigger",
        "nodes": [
            NodeSpec(name="conf", children=["hw", "infra", "algo", "l1_menu"]),
            NodeSpec(
                name="rs",
                category="run_settings",
                format="xml",
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
            NodeSpec(name="algo", category="algo", format="xml"),
            NodeSpec(
                name="infra",
                category="infra",
                format="xml",
                leaves=["mp7", "amc502_extcond", "amc502_finor"],
            ),
            NodeSpec(name="hw", category="hardware", format="xml"),
            NodeSpec(name="l1_menu", format="xml"),
        ],
    },
    "ugmt": {
        "display_name": "uGMT",
        "category": "subsystem",
        "description": "Global Muon Trigger",
        "nodes": [
            NodeSpec(name="conf", children=["hw", "infra", "algo"]),
            NodeSpec(
                name="rs",
                category="run_settings",
                format="xml",
                leaves=["mp7", "mp7_moni", "amc13_moni"],
            ),
            NodeSpec(name="algo", category="algo", format="xml", leaves=["mp7", "luts"]),
            NodeSpec(
                name="infra",
                category="infra",
                format="xml",
                leaves=["amc13", "readoutmenu", "techparams"],
            ),
            NodeSpec(name="hw", category="hardware", format="xml"),
        ],
    },
    "calol1": {
        "display_name": "CaloL1",
        "category": "subsystem",
        "description": "Calorimeter Trigger Layer 1",
        "nodes": [
            NodeSpec(name="conf", children=["hw", "infra", "algo"]),
            NodeSpec(
                name="rs",
                category="run_settings",
                format="xml",
                leaves=["link_masks", "tower_masks", "monitor_settings", "tmt_cycle_config"],
            ),
            NodeSpec(name="algo", category="algo", format="xml"),
            NodeSpec(name="infra", category="infra", format="xml"),
            NodeSpec(name="hw", category="hardware", format="xml"),
        ],
    },
    "calol2": {
        "display_name": "CaloL2",
        "category": "subsystem",
        "description": "Calorimeter Trigger Layer 2",
        "nodes": [
            NodeSpec(name="conf", children=["hw", "infra", "algo"]),
            NodeSpec(
                name="rs",
                category="run_settings",
                format="xml",
                leaves=["monitoring_and_masks", "tmt_redundancy_mode"],
            ),
            NodeSpec(
                name="algo",
                category="algo",
                format="xml",
                leaves=["demux", "mps_common", "mps_jet", "mp_egamma", "mp_sum", "mp_tau"],
            ),
            NodeSpec(
                name="infra",
                category="infra",
                format="xml",
                leaves=["amc13", "mp7", "mps", "demux"],
            ),
            NodeSpec(name="hw", category="hardware", format="xml"),
        ],
    },
    "bmtf": {
        "display_name": "BMTF",
        "category": "subsystem",
        "description": "Barrel Muon Track Finder",
        "nodes": [
            NodeSpec(name="conf", children=["hw", "infra", "algo"]),
            NodeSpec(name="rs", category="run_settings", format="xml", leaves=["amc13", "mp7"]),
            NodeSpec(name="algo", category="algo", format="xml"),
            NodeSpec(name="infra", category="infra", format="xml", leaves=["amc13", "mp7"]),
            NodeSpec(name="hw", category="hardware", format="xml"),
        ],
    },
    "omtf": {
        "display_name": "OMTF",
        "category": "subsystem",
        "description": "Overlap Muon Track Finder",
        "nodes": [
            NodeSpec(name="conf", children=["hw", "infra", "algo"]),
            NodeSpec(name="rs", category="run_settings", format="xml"),
            NodeSpec(name="algo", category="algo", format="xml"),
            NodeSpec(name="infra", category="infra", format="xml"),
            NodeSpec(name="hw", category="hardware", format="xml"),
        ],
    },
    "emtf": {
        "display_name": "EMTF",
        "category": "subsystem",
        "description": "Endcap Muon Track Finder",
        "nodes": [
            NodeSpec(name="conf", children=["hw", "infra", "algo"]),
            NodeSpec(name="rs", category="run_settings", format="xml"),
            NodeSpec(name="algo", category="algo", format="xml"),
            NodeSpec(name="infra", category="infra", format="xml", leaves=["amc13", "mtf7"]),
            NodeSpec(name="hw", category="hardware", format="xml"),
        ],
    },
    "twinmux": {
        "display_name": "TwinMux",
        "category": "subsystem",
        "description": "Adaptive layer for the track finder in the barrel region.",
        "nodes": [
            NodeSpec(name="conf", children=["hw", "infra", "algo"]),
            NodeSpec(name="rs", category="run_settings", format="xml"),
            NodeSpec(name="algo", category="algo", format="xml"),
            NodeSpec(
                name="infra",
                category="infra",
                format="xml",
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
            NodeSpec(name="hw", category="hardware", format="xml"),
        ],
    },
    "spare_ugt": {
        "display_name": "Spare uGT",
        "category": "subsystem",
        "description": "Standby Global Trigger board",
        "nodes": [
            NodeSpec(name="conf", category="hardware", format="xml", leaves=["hw"]),
        ],
    },
    "cppf": {
        "display_name": "CPPF",
        "category": "subsystem",
        "description": "Concentration Pre-Processing and Fan-out",
        "nodes": [
            NodeSpec(name="conf", children=["hw", "infra", "algo"]),
            NodeSpec(name="rs", category="run_settings", format="xml"),
            NodeSpec(name="algo", category="algo", format="xml"),
            NodeSpec(name="infra", category="infra", format="xml"),
            NodeSpec(name="hw", category="hardware", format="xml"),
        ],
    },
}

# (parent subsystem, node, child subsystem, node, alias)
#
# Containment crossing a subsystem boundary.
#
# alias is a legacy column name.
# It is spelled out where one parent needs several distinctly-named pointers at the same child node.
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
    # l1_trg bundles each subsystem's config and run settings directly
    # ugt/rs is pointed at twice so we need an alias for spare_ugt_rs
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
    ("l1_trg", "rs", "ugt", "rs", "spare_ugt_rs"),
    ("spare_ugt", "conf", "ugt", "infra", None),
    ("spare_ugt", "conf", "ugt", "algo", None),
    ("spare_ugt", "conf", "ugt", "l1_menu", None),
]


def _leaf_name(parent: str, leaf: str) -> str:
    return leaf if parent == ROOT_NODE else f"{parent}_{leaf}"


def _subsystem_rows() -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "display_name": spec["display_name"],
            "category": spec["category"],
            "description": spec["description"],
        }
        for name, spec in CATALOG.items()
    ]


def _node_rows(subsystem_ids: dict[str, int]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sub_name, spec in CATALOG.items():
        subsystem_id = subsystem_ids[sub_name]
        for node in spec["nodes"]:
            leaves = node.get("leaves", [])
            rows.append(
                {
                    "subsystem_id": subsystem_id,
                    "name": node["name"],
                    # Category and format is reserved for leaves.
                    "category": None if leaves else node.get("category"),
                    "format": None if leaves else node.get("format"),
                }
            )
            rows.extend(
                {
                    "subsystem_id": subsystem_id,
                    "name": _leaf_name(node["name"], leaf),
                    "category": node.get("category"),
                    "format": node.get("format"),
                }
                for leaf in leaves
            )
    return rows


def _edge_rows(node_ids: dict[tuple[str, str], int]) -> list[dict[str, object]]:
    edges: list[tuple[tuple[str, str], tuple[str, str], str]] = []
    for sub_name, spec in CATALOG.items():
        for node in spec["nodes"]:
            parent = (sub_name, node["name"])
            # Within a subsystem the child's own name is unique already, so it is the alias.
            edges.extend((parent, (sub_name, child), child) for child in node.get("children", []))
            edges.extend(
                (parent, (sub_name, name), name)
                for name in (_leaf_name(node["name"], leaf) for leaf in node.get("leaves", []))
            )
    edges.extend(
        (
            (parent_sub, parent_node),
            (child_sub, child_node),
            alias or f"{child_sub}_{child_node}",
        )
        for parent_sub, parent_node, child_sub, child_node, alias in REFERENCES
    )
    # seed() sends one INSERT, and Postgres refuses to resolve the same conflict twice.
    return [
        {
            "parent_node_id": node_ids[parent],
            "child_node_id": node_ids[child],
            "alias": alias,
        }
        for parent, child, alias in dict.fromkeys(edges)
    ]


def _subsystem_ids() -> dict[str, int]:
    subsystem = table("subsystem", column("id"), column("name"))
    rows = op.get_bind().execute(select(subsystem.c.name, subsystem.c.id))
    return {name: subsystem_id for name, subsystem_id in rows}


def _node_ids() -> dict[tuple[str, str], int]:
    node = table("node", column("id"), column("name"), column("subsystem_id"))
    subsystem = table("subsystem", column("id"), column("name"))
    rows = op.get_bind().execute(
        select(subsystem.c.name, node.c.name, node.c.id).where(
            node.c.subsystem_id == subsystem.c.id
        )
    )
    return {(sub_name, node_name): node_id for sub_name, node_name, node_id in rows}


def upgrade() -> None:
    seed("subsystem", _subsystem_rows(), key=["name"])
    seed("node", _node_rows(_subsystem_ids()), key=["subsystem_id", "name"])
    seed("node_edge", _edge_rows(_node_ids()), key=["parent_node_id", "child_node_id", "alias"])


def downgrade() -> None:
    pass
