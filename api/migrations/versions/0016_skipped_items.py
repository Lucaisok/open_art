"""the artist's "Not needed" on a checklist item: it no longer blocks the download and stays out of
the zip (the extraction can list something the call doesn't ask for).

Revision ID: 0016
Revises: 0015
"""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("application_items", sa.Column("skipped", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("application_items", "skipped")
