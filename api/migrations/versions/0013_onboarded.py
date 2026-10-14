"""when the artist finished the onboarding (Documents -> Profile -> Projects -> "Continue to Discover").
After it the app is Discover, Studio and Account only (workflow.MD, "Studio restructure").
Artists who already saved a profile had finished the onboarding as it was: they count as onboarded.

Revision ID: 0013
Revises: 0012
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarded_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE users SET onboarded_at = now() WHERE id IN (SELECT user_id FROM profiles)")


def downgrade() -> None:
    op.drop_column("users", "onboarded_at")
