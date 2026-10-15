"""the artist's own texts on an application: a title (set only on the texts they added, keys "t-...")
and a creation time, to list them in the order they were added.

Revision ID: 0015
Revises: 0014
"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("application_items", sa.Column("title", sa.String(200)))
    op.add_column("application_items", sa.Column("created_at", sa.DateTime(timezone=True),
                                                 server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_column("application_items", "created_at")
    op.drop_column("application_items", "title")
