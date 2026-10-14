"""an assistant reply that rewrote the draft says so, with the new version's length ("Wrote a new
version · 238 words", the application page's design).

Revision ID: 0014
Revises: 0013
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_messages", sa.Column("wrote_words", sa.Integer()))


def downgrade() -> None:
    op.drop_column("agent_messages", "wrote_words")
