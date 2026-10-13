"""projects and interests, and the suggestions an artist dismissed (workflow.MD, "Projects page")

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("status", sa.String(10)),
        sa.Column("years", sa.String(30)),
        sa.Column("summary", sa.Text()),
        sa.Column("medium", sa.Text()),
        sa.Column("venues", JSONB(), server_default="[]", nullable=False),
        sa.Column("sources", JSONB(), server_default="[]", nullable=False),
        sa.Column("suggestion_key", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "dismissed_suggestions",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("dismissed_suggestions")
    op.drop_table("projects")
