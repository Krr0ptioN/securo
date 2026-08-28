"""materialize imported category paths as an audited hierarchy

Revision ID: 080
Revises: 079
"""
import re
import uuid

from alembic import op
import sqlalchemy as sa

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None

_PREFIX = re.compile(r"^\s*\d+\s+")


def _label(part: str) -> str:
    return _PREFIX.sub("", part).strip()


def upgrade():
    bind = op.get_bind()
    op.create_table(
        "category_hierarchy_migration_audit",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("source_category_id", sa.UUID(), nullable=False),
        sa.Column("target_category_id", sa.UUID(), nullable=False),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("target_path", sa.String(500), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_category_hierarchy_migration_audit_workspace_id", "category_hierarchy_migration_audit", ["workspace_id"])

    rows = bind.execute(sa.text("""
        SELECT id, user_id, workspace_id, group_id, name, icon, color,
               is_system, is_hidden, treat_as_transfer, is_ignored
        FROM categories ORDER BY id
    """)).mappings().all()
    # Cache only nodes built by this migration. This prevents a legacy root
    # named 'Housing' from being mistaken for Life > Housing.
    nodes: dict[tuple[uuid.UUID, uuid.UUID | None, str], uuid.UUID] = {}
    paths: dict[tuple[uuid.UUID, str], uuid.UUID] = {}

    def node(row, parent_id, name):
        key = (row["workspace_id"], parent_id, name)
        if key in nodes:
            return nodes[key]
        node_id = uuid.uuid4()
        bind.execute(sa.text("""
            INSERT INTO categories (id, user_id, workspace_id, group_id, parent_id,
              name, icon, color, is_system, is_hidden, treat_as_transfer, is_ignored)
            VALUES (:id, :user_id, :workspace_id, NULL, :parent_id,
              :name, :icon, :color, false, false, false, false)
        """), {"id": node_id, "user_id": row["user_id"], "workspace_id": row["workspace_id"], "parent_id": parent_id, "name": name, "icon": "folder", "color": "#6B7280"})
        nodes[key] = node_id
        return node_id

    for row in rows:
        source_name = row["name"]
        if "›" not in source_name:
            continue
        parts = [_label(part) for part in source_name.split("›") if _label(part)]
        if len(parts) < 2:
            continue
        parent_id = None
        for part in parts[:-1]:
            parent_id = node(row, parent_id, part)
        leaf = parts[-1]
        bind.execute(sa.text("UPDATE categories SET name=:name, parent_id=:parent_id, group_id=NULL WHERE id=:id"), {"id": row["id"], "name": leaf, "parent_id": parent_id})
        paths[(row["workspace_id"], " / ".join(parts))] = row["id"]
        bind.execute(sa.text("""
            INSERT INTO category_hierarchy_migration_audit
              (id, workspace_id, source_category_id, target_category_id, source_name, target_path, action)
            VALUES (:id, :workspace_id, :source, :target, :name, :path, 'materialized_path')
        """), {"id": uuid.uuid4(), "workspace_id": row["workspace_id"], "source": row["id"], "target": row["id"], "name": source_name, "path": " / ".join(parts)})

    # Only exact, intentional legacy mappings are merged. All other legacy
    # categories remain intact for review instead of being guessed at.
    mapping = {
        "Housing": "Life / Housing",
        "Food & Dining": "Life / Food",
        "Groceries": "Life / Food / Groceries",
        "Transport": "Life / Transport",
        "Istanbul Kart": "Life / Transport / Public Transit",
        "Health": "Life / Health",
        "Education": "Life / Education",
        "Personal Care": "Life / Personal / Personal Care",
        "Leisure": "Life / Personal / Entertainment",
        "Drinking & Fun": "Life / Personal / Entertainment",
        "Transfers": "Life / Finance / Transfers Savings",
    }
    for row in rows:
        target_id = paths.get((row["workspace_id"], mapping.get(row["name"], "")))
        if not target_id:
            continue
        bind.execute(sa.text("UPDATE transactions SET category_id=:target WHERE category_id=:source"), {"source": row["id"], "target": target_id})
        bind.execute(sa.text("UPDATE categories SET is_hidden=true WHERE id=:id"), {"id": row["id"]})
        bind.execute(sa.text("""
            INSERT INTO category_hierarchy_migration_audit
              (id, workspace_id, source_category_id, target_category_id, source_name, target_path, action)
            VALUES (:id, :workspace_id, :source, :target, :name, :path, 'merged_legacy')
        """), {"id": uuid.uuid4(), "workspace_id": row["workspace_id"], "source": row["id"], "target": target_id, "name": row["name"], "path": mapping[row["name"]]})


def downgrade():
    # The audit deliberately preserves the mapping needed for a controlled
    # restore; automatic reversal would lose the transaction reassignment.
    op.drop_table("category_hierarchy_migration_audit")
