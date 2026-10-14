"""the projects chosen for an application, and for one of its texts (workflow.MD, "Step 6", sub-step 7)

Revision ID: 0009
Revises: 0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("projects", JSONB()))
    op.add_column("application_items", sa.Column("projects", JSONB()))


def downgrade() -> None:
    op.drop_column("application_items", "projects")
    op.drop_column("applications", "projects")
