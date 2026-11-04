"""Row Level Security policies and append-only audit log

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "document_types", "folders", "groups", "notifications", "roles", "tenant_modules", "tenant_quotas",
    "tenant_settings", "user_tenants", "documents", "group_members", "metadata_definitions",
    "role_permissions", "user_roles", "document_metadata_values", "document_relations", "document_tags",
    "document_versions", "ocr_pages", "processing_jobs",
]

# A row is visible / writable only when it belongs to the tenant bound to the
# current transaction, unless the platform explicitly opened a bypass session.
POLICY = (
    "(current_setting('app.bypass_rls', true) = 'on') OR "
    "(tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))"
)


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({POLICY}) WITH CHECK ({POLICY})")

    # Audit: tenant rows visible to that tenant; platform rows (tenant_id NULL) only with bypass.
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON audit_logs USING ({POLICY}) WITH CHECK ({POLICY})")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_logs_no_update BEFORE UPDATE OR DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_immutable()")
    for table in [*TENANT_TABLES, "audit_logs"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
