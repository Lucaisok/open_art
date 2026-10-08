"""profiles remember which documents were reviewed (web app step 4b: profile pre-filled from the
artist's documents, by rules)

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("reviewed_documents", JSONB(), server_default="[]", nullable=False))


def downgrade() -> None:
    op.drop_column("profiles", "reviewed_documents")
