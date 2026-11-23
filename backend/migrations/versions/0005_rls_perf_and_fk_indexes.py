"""RLS policies evaluated once per statement (initplan) and indexed foreign keys

Revision ID: 0005
Revises: 0004

* ``current_setting()`` is wrapped in a scalar sub-select so PostgreSQL evaluates it once per
  query instead of once per row (Supabase lint 0003_auth_rls_initplan).
* tenant_id is compared as uuid (not text) so the tenant_id indexes are usable.
* covering indexes for every foreign key flagged by the Supabase performance advisor.
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "document_types", "folders", "groups", "notifications", "roles", "tenant_modules", "tenant_quotas",
    "tenant_settings", "user_tenants", "documents", "group_members", "metadata_definitions", "role_permissions",
    "user_roles", "document_metadata_values", "document_relations", "document_tags", "document_versions",
    "ocr_pages", "processing_jobs", "audit_logs", "document_views", "user_preferences", "object_types",
    "business_objects", "document_object_links", "ai_providers", "ai_prompt_tests", "ai_usage_events",
]
SHARED_TABLES = ["ai_prompts", "ai_prompt_versions"]

BYPASS = "((select current_setting('app.bypass_rls', true)) = 'on')"
OWN = "(tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))"

OLD_BYPASS = "(current_setting('app.bypass_rls', true) = 'on')"
OLD_OWN = "(tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))"

FK_INDEXES = [
    ("ai_prompt_tests", "created_by"), ("ai_prompt_tests", "document_id"), ("ai_prompt_tests", "provider_id"),
    ("ai_prompt_versions", "created_by"), ("ai_providers", "fallback_provider_id"),
    ("business_objects", "created_by"), ("document_metadata_values", "definition_id"),
    ("document_metadata_values", "validated_by"), ("document_object_links", "created_by"),
    ("document_relations", "created_by"), ("document_versions", "author_id"), ("document_views", "created_by"),
    ("document_views", "owner_id"), ("documents", "checked_out_by"), ("documents", "duplicate_of_id"),
    ("documents", "folder_id"), ("documents", "owner_id"), ("folders", "created_by"),
    ("role_permissions", "permission_code"), ("tenants", "plan_id"), ("user_sessions", "tenant_id"),
]


def _policies(bypass: str, own: str) -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({bypass} OR {own}) WITH CHECK ({bypass} OR {own})")
    for table in SHARED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({bypass} OR tenant_id IS NULL OR {own}) "
                   f"WITH CHECK ({bypass} OR {own})")


def upgrade() -> None:
    _policies(BYPASS, OWN)
    for table, column in FK_INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column}_fk ON {table} ({column})")


def downgrade() -> None:
    for table, column in FK_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_{column}_fk")
    _policies(OLD_BYPASS, OLD_OWN)
