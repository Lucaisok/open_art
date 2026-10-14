"""the passages each agent message relied on (workflow.MD, "Step 6", sub-step 4)

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_messages", sa.Column("sources", JSONB(), server_default="[]", nullable=False))


def downgrade() -> None:
    op.drop_column("agent_messages", "sources")
