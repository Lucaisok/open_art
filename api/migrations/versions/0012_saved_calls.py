"""calls the artist saved (workflow.MD, "Saved calls"): the Studio lists them as saved / in draft /
completed / closed. The title and deadline are copied at saving, so a call later gone from the
corpus still shows in the list.

Revision ID: 0012
Revises: 0011
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_calls",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("opportunity_id", sa.String(100), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("deadline", sa.Date()),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # an application already started counts as saved
    op.execute("""
        INSERT INTO saved_calls (user_id, opportunity_id, title)
        SELECT user_id, opportunity_id, opportunity_id FROM applications
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("saved_calls")
