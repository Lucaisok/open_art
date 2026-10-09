"""profiles remember which CV was reviewed (web app step 4b: profile pre-filled from the CV, by rules)

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("reviewed_document_id", sa.Uuid(),
                                        sa.ForeignKey("documents.id", ondelete="SET NULL")))


def downgrade() -> None:
    op.drop_column("profiles", "reviewed_document_id")
