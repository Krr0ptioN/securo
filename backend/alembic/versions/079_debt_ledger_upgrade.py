"""debt interest, receipts, and category hierarchy

Revision ID: 079
Revises: 078
"""
from alembic import op
import sqlalchemy as sa

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("categories", sa.Column("parent_id", sa.UUID(), sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True))
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.add_column("debts", sa.Column("category_id", sa.UUID(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True))
    op.add_column("debts", sa.Column("account_id", sa.UUID(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True))
    op.add_column("debts", sa.Column("annual_interest_rate", sa.Numeric(7, 4), nullable=True))
    op.add_column("debts", sa.Column("interest_start_on", sa.Date(), nullable=True))
    op.add_column("debts", sa.Column("last_accrual_on", sa.Date(), nullable=True))
    op.add_column("debts", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("debt_payments", sa.Column("interest_transaction_id", sa.UUID(), sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True))
    op.add_column("debt_payments", sa.Column("principal_amount", sa.Numeric(15, 2), nullable=False, server_default="0"))
    op.add_column("debt_payments", sa.Column("interest_amount", sa.Numeric(15, 2), nullable=False, server_default="0"))
    op.create_table("debt_receipts", sa.Column("id", sa.UUID(), primary_key=True), sa.Column("debt_payment_id", sa.UUID(), sa.ForeignKey("debt_payments.id", ondelete="CASCADE"), nullable=False), sa.Column("transaction_id", sa.UUID(), sa.ForeignKey("transactions.id", ondelete="SET NULL")), sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False), sa.Column("title", sa.String(255)), sa.Column("category_id", sa.UUID(), sa.ForeignKey("categories.id", ondelete="SET NULL")), sa.Column("tags", sa.String(500)), sa.Column("filename", sa.String(255), nullable=False), sa.Column("storage_key", sa.String(500), nullable=False), sa.Column("content_type", sa.String(255), nullable=False), sa.Column("size", sa.BigInteger(), nullable=False), sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_debt_receipts_debt_payment_id", "debt_receipts", ["debt_payment_id"])
    op.create_index("ix_debt_receipts_workspace_id", "debt_receipts", ["workspace_id"])

def downgrade():
    op.drop_table("debt_receipts")
    for column in ("interest_amount", "principal_amount", "interest_transaction_id"):
        op.drop_column("debt_payments", column)
    for column in ("is_archived", "last_accrual_on", "interest_start_on", "annual_interest_rate", "account_id", "category_id"):
        op.drop_column("debts", column)
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_column("categories", "parent_id")
