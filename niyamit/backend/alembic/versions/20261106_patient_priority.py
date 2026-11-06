"""Staff-assigned clinical follow-up priority."""
from alembic import op
import sqlalchemy as sa
revision="20261106_patient_priority"
down_revision="20261106_demo_billing"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("patient_priorities",
        sa.Column("patient_id",sa.Uuid(),sa.ForeignKey("patients.id"),primary_key=True),
        sa.Column("clinic_id",sa.Uuid(),sa.ForeignKey("clinics.id"),nullable=False),
        sa.Column("priority",sa.String(20),nullable=False),
        sa.Column("reason",sa.String(500),nullable=False),
        sa.Column("readings_hash",sa.String(64),nullable=False),
        sa.Column("assessed_by",sa.String(160),nullable=False),
        sa.Column("assessed_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_patient_priorities_clinic_id","patient_priorities",["clinic_id"])

def downgrade():
    op.drop_table("patient_priorities")
