"""seed roles and their subsystem access for the L1CE catalog

Revision ID: data_seed_legacy_roles
Revises: data_seed_legacy_catalog
Create Date: 2026-08-26 11:26:56.807619

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import column, select, table

from migrations.seed import seed

# revision identifiers, used by Alembic
revision: str = "data_seed_legacy_roles"
down_revision: str | Sequence[str] | None = "data_seed_legacy_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"

# role name + subsystems it is expert for
GRANTS: dict[str, list[str]] = {
    "keytree_ugt_expert": ["ugt"],
    "keytree_ugmt_expert": ["ugmt"],
    "keytree_calol1_expert": ["calol1"],
    "keytree_calol2_expert": ["calol2"],
    "keytree_bmtf_expert": ["bmtf"],
    "keytree_omtf_expert": ["omtf"],
    "keytree_emtf_expert": ["emtf"],
    "keytree_twinmux_expert": ["twinmux"],
    "keytree_spare_ugt_expert": ["spare_ugt"],
    "keytree_cppf_expert": ["cppf"],
    "keytree_tcds_expert": ["tcds"],
    "keytree_l1_trg_doc": ["l1_trg"],
    "keytree_hlt_doc": ["l1_hlt"],
    "keytree_cms_run_coordinator": ["cms_run"],
    "keytree_superuser": [
        "l1_hlt",
        "cms_run",
        "l1_trg",
        "tcds",
        "ugt",
        "ugmt",
        "calol1",
        "calol2",
        "bmtf",
        "omtf",
        "emtf",
        "twinmux",
        "spare_ugt",
        "cppf",
    ],
}


def upgrade() -> None:
    seed("role", [{"name": name} for name in GRANTS], key=["name"])

    role = table("role", column("id"), column("name"))
    subsystem = table("subsystem", column("id"), column("name"))
    bind = op.get_bind()
    role_ids = {name: id for name, id in bind.execute(select(role.c.name, role.c.id))}
    subsystem_ids = {
        name: id for name, id in bind.execute(select(subsystem.c.name, subsystem.c.id))
    }

    seed(
        "role_subsystem",
        [
            {"role_id": role_ids[name], "subsystem_id": subsystem_ids[sub]}
            for name, subs in GRANTS.items()
            for sub in subs
        ],
        key=["role_id", "subsystem_id"],
    )


def downgrade() -> None:
    pass
