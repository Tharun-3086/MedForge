"""Clinic-admin approved, single-use staff invitations."""
from alembic import op
import sqlalchemy as sa

revision = "20261105_staff_invites"
down_revision = "20261104_patient_otp"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("staff_invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("clinic_id", sa.Uuid(), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_staff_invitations_clinic_id", "staff_invitations", ["clinic_id"])


def downgrade():
    op.drop_table("staff_invitations")
