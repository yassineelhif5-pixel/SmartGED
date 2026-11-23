"""Document Splitting Engine: split proposals

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

BYPASS = "((select current_setting('app.bypass_rls', true)) = 'on')"
OWN = "(tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))"
TABLE = "document_split_proposals"


def upgrade() -> None:
    split_status = postgresql.ENUM("proposed", "applied", "dismissed", "superseded", name="split_status",
                                   create_type=False)
    split_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        TABLE,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", split_status, nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("separator_pages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("child_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], name=op.f("fk_document_split_proposals_decided_by_users")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"],
                                name=op.f("fk_document_split_proposals_document_id_documents"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"],
                                name=op.f("fk_document_split_proposals_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_split_proposals")),
    )
    op.create_index("ix_document_split_proposals_document", TABLE, ["document_id", "status"])
    op.create_index("ix_document_split_proposals_decided_by_fk", TABLE, ["decided_by"])
    op.create_index(op.f("ix_document_split_proposals_tenant_id"), TABLE, ["tenant_id"])
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {TABLE} USING ({BYPASS} OR {OWN}) WITH CHECK ({BYPASS} OR {OWN})")


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {TABLE}")
    op.drop_table(TABLE)
    op.execute("DROP TYPE IF EXISTS split_status")
