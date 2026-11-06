"""Persist phone OTP send limits across API restarts."""
from alembic import op
import sqlalchemy as sa

revision = "20261106_otp_send_limits"
down_revision = "20261106_patient_priority"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("patient_otp_challenges", sa.Column("send_window_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("patient_otp_challenges", sa.Column("send_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("patient_otp_challenges", "send_count")
    op.drop_column("patient_otp_challenges", "send_window_started_at")
