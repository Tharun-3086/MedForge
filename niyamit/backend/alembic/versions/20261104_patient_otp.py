"""Persistent, single-use patient OTP challenges."""
from alembic import op
import sqlalchemy as sa
revision = '20261104_patient_otp'
down_revision = '2594b5760c8e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('patient_otp_challenges',
        sa.Column('phone_hash', sa.String(64), primary_key=True),
        sa.Column('id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_table('patient_otp_challenges')
