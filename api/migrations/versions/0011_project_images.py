"""images of the artist's projects: read from their PDFs or uploaded by hand, and chosen for an
application's image item (workflow.MD, "Project images").

Revision ID: 0011
Revises: 0010
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_images",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        # read from this document; kept (SET NULL) once a saved project holds it
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  index=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True),
        sa.Column("page", sa.Integer()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # each page's text lines (to put a work's images with it) and whether images were read yet
    op.add_column("documents", sa.Column("page_lines", JSONB()))
    op.add_column("documents", sa.Column("images_read", sa.Boolean(), nullable=False, server_default="false"))
    # the images chosen for an application's image item
    op.add_column("application_items", sa.Column("images", JSONB()))


def downgrade() -> None:
    op.drop_column("application_items", "images")
    op.drop_column("documents", "images_read")
    op.drop_column("documents", "page_lines")
    op.drop_table("project_images")
