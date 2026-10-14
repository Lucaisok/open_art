"""what a saved project is: a work, an exhibition, a performance or a commission (workflow.MD,
"Plan: projects on the profile page"). Projects saved before are works; interests have none.

Revision ID: 0010
Revises: 0009
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("category", sa.String(12)))
    op.execute("UPDATE projects SET category = 'work' WHERE kind = 'project'")


def downgrade() -> None:
    op.drop_column("projects", "category")
