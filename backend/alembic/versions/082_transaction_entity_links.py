"""add transaction entity context for debt/goal/installment surfaces

Revision ID: 082
Revises: 081
"""
from alembic import op
import sqlalchemy as sa

revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("transactions", sa.Column("related_entity_type", sa.String(32), nullable=True))
    op.add_column("transactions", sa.Column("related_entity_id", sa.UUID(), nullable=True))
    op.add_column("transactions", sa.Column("related_entity_name", sa.String(255), nullable=True))
    op.create_index("ix_transactions_related_entity_type", "transactions", ["related_entity_type"])
    op.create_index("ix_transactions_related_entity_id", "transactions", ["related_entity_id"])
    op.execute(sa.text("""
      UPDATE transactions t SET related_entity_type='loan', related_entity_id=d.id,
        related_entity_name=d.description
      FROM debts d WHERE d.origin_transaction_id=t.id
    """))
    op.execute(sa.text("""
      UPDATE transactions t SET related_entity_type='debt_repayment', related_entity_id=d.id,
        related_entity_name=d.description
      FROM debt_payments p JOIN debts d ON d.id=p.debt_id
      WHERE p.transaction_id=t.id OR p.interest_transaction_id=t.id
    """))

def downgrade():
    op.drop_index("ix_transactions_related_entity_id", table_name="transactions")
    op.drop_index("ix_transactions_related_entity_type", table_name="transactions")
    op.drop_column("transactions", "related_entity_name")
    op.drop_column("transactions", "related_entity_id")
    op.drop_column("transactions", "related_entity_type")
