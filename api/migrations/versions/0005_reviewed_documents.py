"""profiles remember every reviewed document, not just one CV (web app step 4c: practice from documents)

0004 added `reviewed_document_id` (one CV) and was deployed. A later edit changed 0004 in place
to a `reviewed_documents` list, but a database that already ran 0004 never re-runs it, so
production kept the old column and every profile read failed. Lesson: never edit a deployed
migration, add a new one. This one does the change for real.

It checks what is there first, so it also runs cleanly on a local database that applied the
edited 0004 (which already has `reviewed_documents` and no `reviewed_document_id`).

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("profiles")}


def upgrade() -> None:
    columns = _columns()
    if "reviewed_documents" not in columns:
        op.add_column("profiles", sa.Column("reviewed_documents", JSONB(), server_default="[]", nullable=False))
    if "reviewed_document_id" in columns:
        # keep the one reviewed CV, as a one-item list of its id (the same text form api/profile.py stores)
        op.execute("UPDATE profiles SET reviewed_documents = jsonb_build_array(reviewed_document_id::text) "
                   "WHERE reviewed_document_id IS NOT NULL")
        op.drop_column("profiles", "reviewed_document_id")


def downgrade() -> None:
    # back to 0004's shape; only one id fits there, so the list is dropped (suggestions are offered again)
    op.add_column("profiles", sa.Column("reviewed_document_id", sa.Uuid(),
                                        sa.ForeignKey("documents.id", ondelete="SET NULL")))
    op.drop_column("profiles", "reviewed_documents")
