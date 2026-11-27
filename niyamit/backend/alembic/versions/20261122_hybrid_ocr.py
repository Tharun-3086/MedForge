"""Persist OCR routing choices with the original document."""
from alembic import op
import sqlalchemy as sa

revision = "20261122_hybrid_ocr"
down_revision = "20261106_otp_send_limits"
branch_labels = depends_on = None


def upgrade():
    op.add_column("source_artifacts", sa.Column("document_style", sa.String(20), nullable=False, server_default="auto"))
    op.add_column("source_artifacts", sa.Column("document_language", sa.String(10), nullable=False, server_default="en"))


def downgrade():
    op.drop_column("source_artifacts", "document_language")
    op.drop_column("source_artifacts", "document_style")
