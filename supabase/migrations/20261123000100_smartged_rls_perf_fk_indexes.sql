
CREATE SCHEMA IF NOT EXISTS smartged;

SET search_path TO smartged, public;

-- Running upgrade 0004 -> 0005

DROP POLICY IF EXISTS tenant_isolation ON document_types;

CREATE POLICY tenant_isolation ON document_types USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON folders;

CREATE POLICY tenant_isolation ON folders USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON groups;

CREATE POLICY tenant_isolation ON groups USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON notifications;

CREATE POLICY tenant_isolation ON notifications USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON roles;

CREATE POLICY tenant_isolation ON roles USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON tenant_modules;

CREATE POLICY tenant_isolation ON tenant_modules USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON tenant_quotas;

CREATE POLICY tenant_isolation ON tenant_quotas USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON tenant_settings;

CREATE POLICY tenant_isolation ON tenant_settings USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON user_tenants;

CREATE POLICY tenant_isolation ON user_tenants USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON documents;

CREATE POLICY tenant_isolation ON documents USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON group_members;

CREATE POLICY tenant_isolation ON group_members USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON metadata_definitions;

CREATE POLICY tenant_isolation ON metadata_definitions USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON role_permissions;

CREATE POLICY tenant_isolation ON role_permissions USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON user_roles;

CREATE POLICY tenant_isolation ON user_roles USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON document_metadata_values;

CREATE POLICY tenant_isolation ON document_metadata_values USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON document_relations;

CREATE POLICY tenant_isolation ON document_relations USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON document_tags;

CREATE POLICY tenant_isolation ON document_tags USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON document_versions;

CREATE POLICY tenant_isolation ON document_versions USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON ocr_pages;

CREATE POLICY tenant_isolation ON ocr_pages USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON processing_jobs;

CREATE POLICY tenant_isolation ON processing_jobs USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON audit_logs;

CREATE POLICY tenant_isolation ON audit_logs USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON document_views;

CREATE POLICY tenant_isolation ON document_views USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON user_preferences;

CREATE POLICY tenant_isolation ON user_preferences USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON object_types;

CREATE POLICY tenant_isolation ON object_types USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON business_objects;

CREATE POLICY tenant_isolation ON business_objects USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON document_object_links;

CREATE POLICY tenant_isolation ON document_object_links USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON ai_providers;

CREATE POLICY tenant_isolation ON ai_providers USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON ai_prompt_tests;

CREATE POLICY tenant_isolation ON ai_prompt_tests USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON ai_usage_events;

CREATE POLICY tenant_isolation ON ai_usage_events USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON ai_prompts;

CREATE POLICY tenant_isolation ON ai_prompts USING (((select current_setting('app.bypass_rls', true)) = 'on') OR tenant_id IS NULL OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

DROP POLICY IF EXISTS tenant_isolation ON ai_prompt_versions;

CREATE POLICY tenant_isolation ON ai_prompt_versions USING (((select current_setting('app.bypass_rls', true)) = 'on') OR tenant_id IS NULL OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));

CREATE INDEX IF NOT EXISTS ix_ai_prompt_tests_created_by_fk ON ai_prompt_tests (created_by);

CREATE INDEX IF NOT EXISTS ix_ai_prompt_tests_document_id_fk ON ai_prompt_tests (document_id);

CREATE INDEX IF NOT EXISTS ix_ai_prompt_tests_provider_id_fk ON ai_prompt_tests (provider_id);

CREATE INDEX IF NOT EXISTS ix_ai_prompt_versions_created_by_fk ON ai_prompt_versions (created_by);

CREATE INDEX IF NOT EXISTS ix_ai_providers_fallback_provider_id_fk ON ai_providers (fallback_provider_id);

CREATE INDEX IF NOT EXISTS ix_business_objects_created_by_fk ON business_objects (created_by);

CREATE INDEX IF NOT EXISTS ix_document_metadata_values_definition_id_fk ON document_metadata_values (definition_id);

CREATE INDEX IF NOT EXISTS ix_document_metadata_values_validated_by_fk ON document_metadata_values (validated_by);

CREATE INDEX IF NOT EXISTS ix_document_object_links_created_by_fk ON document_object_links (created_by);

CREATE INDEX IF NOT EXISTS ix_document_relations_created_by_fk ON document_relations (created_by);

CREATE INDEX IF NOT EXISTS ix_document_versions_author_id_fk ON document_versions (author_id);

CREATE INDEX IF NOT EXISTS ix_document_views_created_by_fk ON document_views (created_by);

CREATE INDEX IF NOT EXISTS ix_document_views_owner_id_fk ON document_views (owner_id);

CREATE INDEX IF NOT EXISTS ix_documents_checked_out_by_fk ON documents (checked_out_by);

CREATE INDEX IF NOT EXISTS ix_documents_duplicate_of_id_fk ON documents (duplicate_of_id);

CREATE INDEX IF NOT EXISTS ix_documents_folder_id_fk ON documents (folder_id);

CREATE INDEX IF NOT EXISTS ix_documents_owner_id_fk ON documents (owner_id);

CREATE INDEX IF NOT EXISTS ix_folders_created_by_fk ON folders (created_by);

CREATE INDEX IF NOT EXISTS ix_role_permissions_permission_code_fk ON role_permissions (permission_code);

CREATE INDEX IF NOT EXISTS ix_tenants_plan_id_fk ON tenants (plan_id);

CREATE INDEX IF NOT EXISTS ix_user_sessions_tenant_id_fk ON user_sessions (tenant_id);

UPDATE smartged.alembic_version SET version_num='0005' WHERE smartged.alembic_version.version_num = '0004';


