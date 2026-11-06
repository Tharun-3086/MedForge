"""Demo clinic subscriptions, no payment collection."""
from alembic import op
import sqlalchemy as sa
revision="20261106_demo_billing"
down_revision="20261105_staff_invites"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("clinic_subscriptions",
        sa.Column("clinic_id",sa.Uuid(),sa.ForeignKey("clinics.id"),primary_key=True),
        sa.Column("plan_key",sa.String(30),nullable=False),
        sa.Column("period_start",sa.Date(),nullable=False),
        sa.Column("period_end",sa.Date(),nullable=False),
        sa.Column("invoices",sa.JSON(),nullable=False))

def downgrade():
    op.drop_table("clinic_subscriptions")
