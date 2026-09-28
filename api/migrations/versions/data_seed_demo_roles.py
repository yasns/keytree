"""seed roles and their subsystem access for the L1CE catalog

Revision ID: data_seed_demo_roles
Revises: data_seed_legacy_catalog
Create Date: 2026-08-26 11:26:56.807619

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import column, select, table

from migrations.seed import subsystem_ids, upsert

# revision identifiers, used by Alembic
revision: str = "data_seed_demo_roles"
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
    "keytree_l1_trg_expert": ["l1_trg"],
    "keytree_l1_hlt_expert": ["l1_hlt"],
    "keytree_cms_run_expert": ["cms_run"],
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

# role name + e-group notification email (ugt e-group covers spare ugt too)
EMAILS: dict[str, str] = {
    "keytree_ugt_expert": "keytree-ugt@cern.ch",
    "keytree_spare_ugt_expert": "keytree-ugt@cern.ch",
    "keytree_ugmt_expert": "keytree-ugmt@cern.ch",
    "keytree_calol1_expert": "keytree-calol1@cern.ch",
    "keytree_calol2_expert": "keytree-calol2@cern.ch",
    "keytree_bmtf_expert": "keytree-bmtf@cern.ch",
    "keytree_omtf_expert": "keytree-omtf@cern.ch",
    "keytree_emtf_expert": "keytree-emtf@cern.ch",
    "keytree_twinmux_expert": "keytree-twinmux@cern.ch",
    "keytree_cppf_expert": "keytree-cppf@cern.ch",
    "keytree_tcds_expert": "keytree-tcds@cern.ch",
    "keytree_l1_trg_expert": "keytree-l1t@cern.ch",
    "keytree_l1_hlt_expert": "keytree-l1-hlt@cern.ch",
    "keytree_cms_run_expert": "keytree-cms-run@cern.ch",
    "keytree_superuser": "keytree-admins@cern.ch",
}


def upgrade() -> None:
    upsert(
        "role",
        [{"cern_role_name": name, "notification_email": EMAILS.get(name)} for name in GRANTS],
        key=["cern_role_name"],
    )

    role = table("role", column("id"), column("cern_role_name"))
    bind = op.get_bind()
    role_ids = {name: id for name, id in bind.execute(select(role.c.cern_role_name, role.c.id))}
    sub_ids = subsystem_ids(bind)

    upsert(
        "role_subsystem",
        [
            {"role_id": role_ids[name], "subsystem_id": sub_ids[sub]}
            for name, subs in GRANTS.items()
            for sub in subs
        ],
        key=["role_id", "subsystem_id"],
    )


def downgrade() -> None:
    pass
