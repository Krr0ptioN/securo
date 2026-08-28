"""link debts to their originating cash transaction

Revision ID: 078
Revises: 077
"""
from alembic import op
import sqlalchemy as sa
revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None
def upgrade():
    op.add_column("debts", sa.Column("origin_transaction_id", sa.UUID(), sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True))
def downgrade():
    op.drop_column("debts", "origin_transaction_id")
