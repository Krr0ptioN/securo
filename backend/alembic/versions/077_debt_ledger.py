"""add debt ledger

Revision ID: 077
Revises: 076
"""
from alembic import op
import sqlalchemy as sa

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("debts", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False), sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("payee_id", sa.UUID(), sa.ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False), sa.Column("direction", sa.String(12), nullable=False), sa.Column("description", sa.String(500), nullable=False), sa.Column("principal", sa.Numeric(15,2), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("opened_on", sa.Date(), nullable=False), sa.Column("due_on", sa.Date()), sa.Column("notes", sa.Text()), sa.Column("status", sa.String(12), nullable=False, server_default="open"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.CheckConstraint("direction in ('receivable','payable')"), sa.CheckConstraint("principal > 0"))
    op.create_index("ix_debts_workspace_id", "debts", ["workspace_id"])
    op.create_table("debt_payments", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("debt_id", sa.UUID(), sa.ForeignKey("debts.id", ondelete="CASCADE"), nullable=False), sa.Column("transaction_id", sa.UUID(), sa.ForeignKey("transactions.id", ondelete="SET NULL")), sa.Column("amount", sa.Numeric(15,2), nullable=False), sa.Column("paid_on", sa.Date(), nullable=False), sa.Column("notes", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.CheckConstraint("amount > 0"))
    op.create_index("ix_debt_payments_debt_id", "debt_payments", ["debt_id"])

def downgrade():
    op.drop_table("debt_payments")
    op.drop_table("debts")
