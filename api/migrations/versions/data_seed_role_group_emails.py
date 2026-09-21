"""seed role group emails

Revision ID: data_seed_role_group_emails
Revises: data_seed_v1_keys
Create Date: 2026-09-20 21:39:37.647790

"""

from collections.abc import Sequence

from migrations.seed import seed

# revision identifiers, used by Alembic
revision: str = "data_seed_role_group_emails"
down_revision: str | Sequence[str] | None = "data_seed_v1_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "schema_tables"


def upgrade() -> None:
    seed(
        "role",
        [{"cern_role_name": "keytree_superuser", "notification_email": "keytree-admins@cern.ch"}],
        key=["cern_role_name"],
    )


def downgrade() -> None:
    pass
