"""Seed normalized taxonomy visuals and merge legacy category labels.

This migration is limited to schema-owned category metadata and references.
It does not embed or export production financial records; all updates are
scoped to the workspace rows present in the target database.

Revision ID: 081
Revises: 080
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, workspace_id, parent_id, name FROM categories")).mappings().all()
    by_key = {(row["workspace_id"], row["parent_id"], row["name"]): row for row in rows}

    def find(workspace_id, names):
        parent = None
        for name in names:
            row = by_key.get((workspace_id, parent, name))
            if not row:
                return None
            parent = row["id"]
        return row

    def audit(source, target, action):
        bind.execute(sa.text("""
            INSERT INTO category_hierarchy_migration_audit
              (id, workspace_id, source_category_id, target_category_id, source_name, target_path, action)
            VALUES (:id, :workspace_id, :source, :target, :name, :path, :action)
        """), {"id": uuid.uuid4(), "workspace_id": source["workspace_id"], "source": source["id"], "target": target["id"], "name": source["name"], "path": target["name"], "action": action})

    # Retire exact duplicates and preserve their historical transaction links.
    exact = {
        "Housing": ["Life", "Housing"], "Food & Dining": ["Life", "Food"],
        "Health": ["Life", "Health"], "Education": ["Life", "Education"],
        "Transport": ["Life", "Transport"], "Groceries": ["Life", "Food", "Groceries"],
        "Istanbul Kart": ["Life", "Transport", "Public Transit"],
        "Leisure": ["Life", "Personal", "Entertainment"],
        "Drinking & Fun": ["Life", "Personal", "Entertainment"],
        "Personal Care": ["Life", "Personal", "Personal Care"],
        "Transfers": ["Life", "Finance", "Transfers Savings"],
        "Other": ["Shared", "Contingency & Misc"],
    }
    for source in rows:
        if source["parent_id"] is not None or source["name"] not in exact:
            continue
        target = find(source["workspace_id"], exact[source["name"]])
        if not target or target["id"] == source["id"]:
            continue
        bind.execute(sa.text("UPDATE transactions SET category_id=:target WHERE category_id=:source"), {"target": target["id"], "source": source["id"]})
        bind.execute(sa.text("UPDATE categories SET is_hidden=true, group_id=NULL WHERE id=:id"), {"id": source["id"]})
        audit(source, target, "merged_duplicate")

    # Legacy categories without an exact imported equivalent become useful
    # children of the canonical tree instead of remaining competing roots.
    relocate = {
        "Salary & Income": (["Life"], "Income & Earnings"),
        "Donations": (["Life", "Personal"], "Donations"),
        "Shopping": (["Life", "Personal"], "General Shopping"),
        "Subscriptions": (["Life", "Personal"], "Subscriptions"),
        "Investments": (["Life", "Finance"], "Investments"),
        "Taxes & Fees": (["Life", "Finance"], "Taxes & Fees"),
    }
    for source in rows:
        if source["parent_id"] is not None or source["name"] not in relocate:
            continue
        parent_names, new_name = relocate[source["name"]]
        parent = find(source["workspace_id"], parent_names)
        if not parent:
            continue
        bind.execute(sa.text("UPDATE categories SET parent_id=:parent, group_id=NULL, name=:name WHERE id=:id"), {"parent": parent["id"], "name": new_name, "id": source["id"]})
        audit(source, parent, "relocated_legacy")

    # Category groups are no longer a presentation hierarchy. Keep their rows
    # for compatibility, but category placement is entirely parent_id based.
    bind.execute(sa.text("UPDATE categories SET group_id=NULL"))

    # Hide the test taxonomy without deleting any history.
    test_roots = [row["id"] for row in rows if row["parent_id"] is None and row["name"] == "TEST"]
    for root in test_roots:
        bind.execute(sa.text("""
            WITH RECURSIVE descendants AS (
              SELECT id FROM categories WHERE id=:root
              UNION ALL SELECT c.id FROM categories c JOIN descendants d ON c.parent_id=d.id
            ) UPDATE categories SET is_hidden=true WHERE id IN (SELECT id FROM descendants)
        """), {"root": root})

    # Semantic icon and color palette. Branch icons identify the type of work;
    # all leaves inherit a meaningful visual rather than the import placeholder.
    styles = {
        "Life": ("heart", "#8B5CF6"), "Business": ("briefcase-business", "#0EA5E9"), "Shared": ("users", "#64748B"),
        "Housing": ("house", "#8B5CF6"), "Food": ("utensils-crossed", "#F59E0B"), "Transport": ("car", "#3B82F6"),
        "Health": ("heart-pulse", "#EF4444"), "Education": ("book-open", "#22C55E"), "Personal": ("user-round", "#EC4899"), "Finance": ("landmark", "#64748B"),
        "AI & Compute": ("bot", "#8B5CF6"), "Software": ("code-2", "#3B82F6"), "Infrastructure": ("server", "#0EA5E9"),
        "Distribution": ("store", "#F97316"), "Marketing": ("megaphone", "#EC4899"), "Hardware": ("monitor", "#64748B"),
        "Production": ("clapperboard", "#A855F7"), "Admin": ("folder-kanban", "#78716C"), "Learning": ("graduation-cap", "#22C55E"),
        "Rent": ("house", "#8B5CF6"), "Utilities": ("zap", "#F59E0B"), "Internet Home": ("wifi", "#3B82F6"),
        "Groceries": ("shopping-cart", "#10B981"), "Eating Out": ("utensils", "#F59E0B"), "Fuel & Vehicle": ("fuel", "#F97316"),
        "Public Transit": ("bus", "#3B82F6"), "Ride Share": ("car-taxi-front", "#3B82F6"), "Fitness": ("dumbbell", "#22C55E"),
        "Insurance": ("shield-check", "#0EA5E9"), "Medical & Pharmacy": ("stethoscope", "#EF4444"), "Clothing": ("shirt", "#EC4899"),
        "Entertainment": ("gamepad-2", "#EC4899"), "Mobile Phone": ("smartphone", "#6366F1"), "Personal Care": ("scissors", "#EC4899"),
        "Banking Fees": ("landmark", "#64748B"), "Debt & Loan Payments": ("hand-coins", "#64748B"), "Transfers Savings": ("arrow-left-right", "#64748B"),
        "Income & Earnings": ("banknote", "#16A34A"), "Investments": ("trending-up", "#0EA5E9"), "Taxes & Fees": ("receipt-text", "#78716C"),
        "Contingency & Misc": ("shield-alert", "#F59E0B"), "FX & Payment Processing": ("badge-dollar-sign", "#64748B"),
        "AI API Usage Overage": ("braces", "#8B5CF6"), "Cloud GPU & Inference": ("cloud-cog", "#8B5CF6"), "Image Video AI": ("image", "#8B5CF6"), "LLM Subscriptions": ("message-square-text", "#8B5CF6"), "Voice Audio AI": ("mic", "#8B5CF6"),
        "Analytics & Crash": ("chart-no-axes-combined", "#3B82F6"), "Design & Creative": ("palette", "#3B82F6"), "Game Engines & Middleware": ("puzzle", "#3B82F6"), "IDEs & Dev Tools": ("code-2", "#3B82F6"), "Productivity SaaS": ("briefcase", "#3B82F6"),
        "CI CD & Registry": ("git-branch", "#0EA5E9"), "Domains & DNS": ("globe", "#0EA5E9"), "Email & Auth": ("key-round", "#0EA5E9"), "Object Storage CDN": ("hard-drive", "#0EA5E9"), "VPS & Hosting": ("server", "#0EA5E9"),
        "Licensing Keys": ("key", "#F97316"), "Store Commissions": ("percent", "#F97316"), "Store Developer Fees": ("badge-dollar-sign", "#F97316"),
        "ASO & Store Tools": ("chart-no-axes-combined", "#EC4899"), "Content & Social Promo": ("share-2", "#EC4899"), "Influencers & Creators": ("users", "#EC4899"), "User Acquisition Ads": ("megaphone", "#EC4899"),
        "Audio Video Capture": ("video", "#64748B"), "Computer & Peripherals": ("monitor", "#64748B"), "Phones & Test Devices": ("smartphone", "#64748B"),
        "Asset Stores Packs": ("package", "#A855F7"), "Freelancers Contractors": ("users-round", "#A855F7"), "Music SFX Licenses": ("music", "#A855F7"),
        "Accounting & Bookkeeping": ("receipt-text", "#78716C"), "Business Registration Fees": ("file-badge", "#78716C"), "Insurance Business": ("shield-check", "#78716C"), "Legal & Contracts": ("scale", "#78716C"), "Taxes & Withholding": ("landmark", "#78716C"),
        "Books Technical": ("book-open", "#22C55E"), "Conferences Meetups": ("users", "#22C55E"), "Pro Courses Certs": ("badge-check", "#22C55E"),
    }
    for name, (icon, color) in styles.items():
        bind.execute(sa.text("UPDATE categories SET icon=:icon, color=:color WHERE name=:name"), {"icon": icon, "color": color, "name": name})

    # Principal movements must stay out of income/expense reporting after the
    # duplicate merge moved historical transfers to the canonical node.
    for workspace_id in {row["workspace_id"] for row in rows}:
        for path in (["Life", "Finance", "Transfers Savings"], ["Life", "Finance", "Debt & Loan Payments"]):
            category = find(workspace_id, path)
            if category:
                bind.execute(sa.text("UPDATE categories SET treat_as_transfer=true WHERE id=:id"), {"id": category["id"]})


def downgrade():
    # Normalization is deliberately non-destructive. The migration audit and
    # pre-migration backup provide a reviewable restore path.
    pass
