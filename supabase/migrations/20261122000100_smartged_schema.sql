
CREATE SCHEMA IF NOT EXISTS smartged;

SET search_path TO smartged, public;

CREATE TABLE smartged.alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE audit_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY, 
    tenant_id UUID, 
    actor_user_id UUID, 
    actor_email VARCHAR(320), 
    action VARCHAR(80) NOT NULL, 
    resource_type VARCHAR(60), 
    resource_id VARCHAR(80), 
    outcome VARCHAR(20) NOT NULL, 
    ip_address VARCHAR(64), 
    user_agent VARCHAR(400), 
    request_id VARCHAR(64), 
    details JSONB, 
    prev_hash VARCHAR(64), 
    hash VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_audit_logs PRIMARY KEY (id)
);

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

CREATE INDEX ix_audit_logs_actor_user_id ON audit_logs (actor_user_id);

CREATE INDEX ix_audit_logs_tenant_created ON audit_logs (tenant_id, created_at);

CREATE INDEX ix_audit_logs_tenant_id ON audit_logs (tenant_id);

CREATE TABLE permissions (
    code VARCHAR(80) NOT NULL, 
    resource VARCHAR(40) NOT NULL, 
    action VARCHAR(40) NOT NULL, 
    description VARCHAR(300), 
    id UUID NOT NULL, 
    CONSTRAINT pk_permissions PRIMARY KEY (id), 
    CONSTRAINT uq_permissions_code UNIQUE (code)
);

CREATE TABLE subscription_plans (
    code VARCHAR(50) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    description VARCHAR(500), 
    max_users INTEGER NOT NULL, 
    max_storage_bytes BIGINT NOT NULL, 
    monthly_ai_credits INTEGER NOT NULL, 
    modules JSONB NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_subscription_plans PRIMARY KEY (id), 
    CONSTRAINT uq_subscription_plans_code UNIQUE (code)
);

CREATE TABLE system_settings (
    key VARCHAR(120) NOT NULL, 
    value JSONB NOT NULL, 
    description VARCHAR(500), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_system_settings PRIMARY KEY (id), 
    CONSTRAINT uq_system_settings_key UNIQUE (key)
);

CREATE TYPE platform_role AS ENUM ('super_admin', 'support_admin', 'auditor');

CREATE TABLE users (
    email VARCHAR(320) NOT NULL, 
    full_name VARCHAR(200) NOT NULL, 
    password_hash VARCHAR(255), 
    platform_role platform_role, 
    is_active BOOLEAN NOT NULL, 
    mfa_enabled BOOLEAN NOT NULL, 
    locale VARCHAR(10) NOT NULL, 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    password_changed_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE TYPE tenant_status AS ENUM ('provisioning', 'active', 'suspended', 'archived');

CREATE TABLE tenants (
    slug VARCHAR(63) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    status tenant_status NOT NULL, 
    plan_id UUID, 
    storage_provider VARCHAR(30) NOT NULL, 
    suspended_at TIMESTAMP WITH TIME ZONE, 
    archived_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_tenants PRIMARY KEY (id), 
    CONSTRAINT fk_tenants_plan_id_subscription_plans FOREIGN KEY(plan_id) REFERENCES subscription_plans (id), 
    CONSTRAINT uq_tenants_slug UNIQUE (slug)
);

CREATE TABLE document_types (
    code VARCHAR(60) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    description VARCHAR(1000), 
    color VARCHAR(20), 
    icon VARCHAR(40), 
    schema_version INTEGER NOT NULL, 
    requires_validation BOOLEAN NOT NULL, 
    classification_hints TEXT, 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_document_types PRIMARY KEY (id), 
    CONSTRAINT fk_document_types_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_document_types_tenant_id_code UNIQUE (tenant_id, code)
);

CREATE INDEX ix_document_types_tenant_id ON document_types (tenant_id);

CREATE TABLE folders (
    parent_id UUID, 
    name VARCHAR(255) NOT NULL, 
    description VARCHAR(1000), 
    created_by UUID, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_folders PRIMARY KEY (id), 
    CONSTRAINT fk_folders_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT fk_folders_parent_id_folders FOREIGN KEY(parent_id) REFERENCES folders (id) ON DELETE CASCADE, 
    CONSTRAINT fk_folders_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE INDEX ix_folders_deleted_at ON folders (deleted_at);

CREATE INDEX ix_folders_parent_id ON folders (parent_id);

CREATE INDEX ix_folders_tenant_id ON folders (tenant_id);

CREATE UNIQUE INDEX uq_folders_tenant_parent_name_live ON folders (tenant_id, coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(name)) WHERE deleted_at IS NULL;

CREATE TABLE groups (
    name VARCHAR(120) NOT NULL, 
    description VARCHAR(500), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_groups PRIMARY KEY (id), 
    CONSTRAINT fk_groups_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_groups_tenant_id_name UNIQUE (tenant_id, name)
);

CREATE INDEX ix_groups_tenant_id ON groups (tenant_id);

CREATE TABLE notifications (
    user_id UUID NOT NULL, 
    kind VARCHAR(60) NOT NULL, 
    title VARCHAR(300) NOT NULL, 
    body VARCHAR(2000), 
    link VARCHAR(500), 
    is_read BOOLEAN NOT NULL, 
    data JSONB, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_notifications PRIMARY KEY (id), 
    CONSTRAINT fk_notifications_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_notifications_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_notifications_tenant_id ON notifications (tenant_id);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE TABLE roles (
    code VARCHAR(60) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    description VARCHAR(500), 
    is_system BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_roles PRIMARY KEY (id), 
    CONSTRAINT fk_roles_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_roles_tenant_id_code UNIQUE (tenant_id, code)
);

CREATE INDEX ix_roles_tenant_id ON roles (tenant_id);

CREATE TABLE tenant_modules (
    module VARCHAR(60) NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_tenant_modules PRIMARY KEY (id), 
    CONSTRAINT fk_tenant_modules_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_tenant_modules_tenant_id_module UNIQUE (tenant_id, module)
);

CREATE INDEX ix_tenant_modules_tenant_id ON tenant_modules (tenant_id);

CREATE TABLE tenant_quotas (
    metric VARCHAR(60) NOT NULL, 
    limit_value BIGINT NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_tenant_quotas PRIMARY KEY (id), 
    CONSTRAINT fk_tenant_quotas_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_tenant_quotas_tenant_id_metric UNIQUE (tenant_id, metric)
);

CREATE INDEX ix_tenant_quotas_tenant_id ON tenant_quotas (tenant_id);

CREATE TABLE tenant_settings (
    key VARCHAR(120) NOT NULL, 
    value JSONB NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_tenant_settings PRIMARY KEY (id), 
    CONSTRAINT fk_tenant_settings_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_tenant_settings_tenant_id_key UNIQUE (tenant_id, key)
);

CREATE INDEX ix_tenant_settings_tenant_id ON tenant_settings (tenant_id);

CREATE TABLE user_sessions (
    user_id UUID NOT NULL, 
    tenant_id UUID, 
    token_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    ip_address VARCHAR(64), 
    user_agent VARCHAR(400), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_user_sessions PRIMARY KEY (id), 
    CONSTRAINT fk_user_sessions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_user_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_user_sessions_token_hash UNIQUE (token_hash)
);

CREATE INDEX ix_user_sessions_user_id ON user_sessions (user_id);

CREATE TYPE membership_status AS ENUM ('invited', 'active', 'disabled');

CREATE TABLE user_tenants (
    user_id UUID NOT NULL, 
    status membership_status NOT NULL, 
    department VARCHAR(120), 
    job_title VARCHAR(120), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_user_tenants PRIMARY KEY (id), 
    CONSTRAINT fk_user_tenants_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_user_tenants_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_user_tenants_tenant_id_user_id UNIQUE (tenant_id, user_id)
);

CREATE INDEX ix_user_tenants_tenant_id ON user_tenants (tenant_id);

CREATE INDEX ix_user_tenants_user_id ON user_tenants (user_id);

CREATE TYPE document_status AS ENUM ('uploaded', 'processing', 'pending_validation', 'published', 'rejected', 'archived', 'failed');

CREATE TYPE step_status AS ENUM ('pending', 'running', 'completed', 'failed', 'skipped', 'not_configured');

CREATE TABLE documents (
    folder_id UUID, 
    parent_document_id UUID, 
    document_type_id UUID, 
    title VARCHAR(500) NOT NULL, 
    file_name VARCHAR(500) NOT NULL, 
    original_file_name VARCHAR(500) NOT NULL, 
    mime_type VARCHAR(150) NOT NULL, 
    extension VARCHAR(20) NOT NULL, 
    file_size BIGINT NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    page_count INTEGER, 
    storage_provider VARCHAR(30) NOT NULL, 
    storage_path VARCHAR(1000) NOT NULL, 
    current_version INTEGER NOT NULL, 
    owner_id UUID, 
    status document_status NOT NULL, 
    language VARCHAR(10), 
    content_text TEXT, 
    duplicate_of_id UUID, 
    scan_status step_status NOT NULL, 
    ocr_status step_status NOT NULL, 
    ai_status step_status NOT NULL, 
    classification_status step_status NOT NULL, 
    validation_status step_status NOT NULL, 
    classification_confidence FLOAT, 
    checked_out_by UUID, 
    checked_out_at TIMESTAMP WITH TIME ZONE, 
    archived_at TIMESTAMP WITH TIME ZONE, 
    search_vector TSVECTOR GENERATED ALWAYS AS (setweight(to_tsvector('simple', coalesce(title, '')), 'A') || setweight(to_tsvector('simple', coalesce(original_file_name, '')), 'B') || setweight(to_tsvector('simple', coalesce(left(content_text, 200000), '')), 'C')) STORED, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_documents PRIMARY KEY (id), 
    CONSTRAINT fk_documents_checked_out_by_users FOREIGN KEY(checked_out_by) REFERENCES users (id), 
    CONSTRAINT fk_documents_document_type_id_document_types FOREIGN KEY(document_type_id) REFERENCES document_types (id) ON DELETE SET NULL, 
    CONSTRAINT fk_documents_duplicate_of_id_documents FOREIGN KEY(duplicate_of_id) REFERENCES documents (id) ON DELETE SET NULL, 
    CONSTRAINT fk_documents_folder_id_folders FOREIGN KEY(folder_id) REFERENCES folders (id) ON DELETE SET NULL, 
    CONSTRAINT fk_documents_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id), 
    CONSTRAINT fk_documents_parent_document_id_documents FOREIGN KEY(parent_document_id) REFERENCES documents (id) ON DELETE SET NULL, 
    CONSTRAINT fk_documents_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE INDEX ix_documents_deleted_at ON documents (deleted_at);

CREATE INDEX ix_documents_document_type_id ON documents (document_type_id);

CREATE INDEX ix_documents_parent_document_id ON documents (parent_document_id);

CREATE INDEX ix_documents_search ON documents USING gin (search_vector);

CREATE INDEX ix_documents_tenant_folder ON documents (tenant_id, folder_id);

CREATE INDEX ix_documents_tenant_id ON documents (tenant_id);

CREATE INDEX ix_documents_tenant_sha256 ON documents (tenant_id, sha256);

CREATE TABLE group_members (
    group_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_group_members PRIMARY KEY (id), 
    CONSTRAINT fk_group_members_group_id_groups FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE CASCADE, 
    CONSTRAINT fk_group_members_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_group_members_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_group_members_group_id_user_id UNIQUE (group_id, user_id)
);

CREATE INDEX ix_group_members_group_id ON group_members (group_id);

CREATE INDEX ix_group_members_tenant_id ON group_members (tenant_id);

CREATE INDEX ix_group_members_user_id ON group_members (user_id);

CREATE TYPE metadata_data_type AS ENUM ('text', 'long_text', 'integer', 'decimal', 'currency', 'date', 'datetime', 'boolean', 'dropdown', 'multi_select', 'reference', 'calculated');

CREATE TABLE metadata_definitions (
    document_type_id UUID NOT NULL, 
    technical_name VARCHAR(80) NOT NULL, 
    display_name VARCHAR(120) NOT NULL, 
    description VARCHAR(1000), 
    data_type metadata_data_type NOT NULL, 
    required BOOLEAN NOT NULL, 
    default_value JSONB, 
    validation_rules JSONB NOT NULL, 
    allowed_values JSONB, 
    searchable BOOLEAN NOT NULL, 
    visible BOOLEAN NOT NULL, 
    ai_extraction_enabled BOOLEAN NOT NULL, 
    extraction_prompt TEXT, 
    sensitive BOOLEAN NOT NULL, 
    requires_human_validation BOOLEAN NOT NULL, 
    position INTEGER NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_metadata_definitions PRIMARY KEY (id), 
    CONSTRAINT fk_metadata_definitions_document_type_id_document_types FOREIGN KEY(document_type_id) REFERENCES document_types (id) ON DELETE CASCADE, 
    CONSTRAINT fk_metadata_definitions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_metadata_definitions_document_type_id_technical_name UNIQUE (document_type_id, technical_name)
);

CREATE INDEX ix_metadata_definitions_document_type_id ON metadata_definitions (document_type_id);

CREATE INDEX ix_metadata_definitions_tenant_id ON metadata_definitions (tenant_id);

CREATE TABLE role_permissions (
    role_id UUID NOT NULL, 
    permission_code VARCHAR(80) NOT NULL, 
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_role_permissions PRIMARY KEY (id), 
    CONSTRAINT fk_role_permissions_permission_code_permissions FOREIGN KEY(permission_code) REFERENCES permissions (code) ON DELETE CASCADE, 
    CONSTRAINT fk_role_permissions_role_id_roles FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
    CONSTRAINT fk_role_permissions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_role_permissions_role_id_permission_code UNIQUE (role_id, permission_code)
);

CREATE INDEX ix_role_permissions_role_id ON role_permissions (role_id);

CREATE INDEX ix_role_permissions_tenant_id ON role_permissions (tenant_id);

CREATE TABLE user_roles (
    user_id UUID NOT NULL, 
    role_id UUID NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_user_roles PRIMARY KEY (id), 
    CONSTRAINT fk_user_roles_role_id_roles FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
    CONSTRAINT fk_user_roles_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_user_roles_tenant_id_user_id_role_id UNIQUE (tenant_id, user_id, role_id)
);

CREATE INDEX ix_user_roles_role_id ON user_roles (role_id);

CREATE INDEX ix_user_roles_tenant_id ON user_roles (tenant_id);

CREATE INDEX ix_user_roles_user_id ON user_roles (user_id);

CREATE TABLE document_metadata_values (
    document_id UUID NOT NULL, 
    definition_id UUID NOT NULL, 
    value JSONB, 
    source VARCHAR(20) NOT NULL, 
    confidence FLOAT, 
    source_page INTEGER, 
    source_text TEXT, 
    validation_status step_status NOT NULL, 
    validated_by UUID, 
    validated_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_document_metadata_values PRIMARY KEY (id), 
    CONSTRAINT fk_document_metadata_values_definition_id_metadata_definitions FOREIGN KEY(definition_id) REFERENCES metadata_definitions (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_metadata_values_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_metadata_values_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_metadata_values_validated_by_users FOREIGN KEY(validated_by) REFERENCES users (id), 
    CONSTRAINT uq_document_metadata_values_document_id_definition_id UNIQUE (document_id, definition_id)
);

CREATE INDEX ix_document_metadata_values_document_id ON document_metadata_values (document_id);

CREATE INDEX ix_document_metadata_values_tenant_id ON document_metadata_values (tenant_id);

CREATE TABLE document_relations (
    source_document_id UUID NOT NULL, 
    target_document_id UUID NOT NULL, 
    relation_type VARCHAR(40) NOT NULL, 
    created_by UUID, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_document_relations PRIMARY KEY (id), 
    CONSTRAINT fk_document_relations_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT fk_document_relations_source_document_id_documents FOREIGN KEY(source_document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_relations_target_document_id_documents FOREIGN KEY(target_document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_relations_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_document_relations_source_document_id_target_documen_24e6 UNIQUE (source_document_id, target_document_id, relation_type)
);

CREATE INDEX ix_document_relations_source_document_id ON document_relations (source_document_id);

CREATE INDEX ix_document_relations_target_document_id ON document_relations (target_document_id);

CREATE INDEX ix_document_relations_tenant_id ON document_relations (tenant_id);

CREATE TABLE document_tags (
    document_id UUID NOT NULL, 
    tag VARCHAR(80) NOT NULL, 
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_document_tags PRIMARY KEY (id), 
    CONSTRAINT fk_document_tags_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_tags_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_document_tags_document_id_tag UNIQUE (document_id, tag)
);

CREATE INDEX ix_document_tags_document_id ON document_tags (document_id);

CREATE INDEX ix_document_tags_tenant_id ON document_tags (tenant_id);

CREATE INDEX ix_document_tags_tenant_tag ON document_tags (tenant_id, tag);

CREATE TABLE document_versions (
    document_id UUID NOT NULL, 
    version_number INTEGER NOT NULL, 
    author_id UUID, 
    comment VARCHAR(1000), 
    change_reason VARCHAR(500), 
    file_name VARCHAR(500) NOT NULL, 
    mime_type VARCHAR(150) NOT NULL, 
    file_size BIGINT NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    storage_path VARCHAR(1000) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_document_versions PRIMARY KEY (id), 
    CONSTRAINT fk_document_versions_author_id_users FOREIGN KEY(author_id) REFERENCES users (id), 
    CONSTRAINT fk_document_versions_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_versions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_document_versions_document_id_version_number UNIQUE (document_id, version_number)
);

CREATE INDEX ix_document_versions_document_id ON document_versions (document_id);

CREATE INDEX ix_document_versions_tenant_id ON document_versions (tenant_id);

CREATE TABLE ocr_pages (
    document_id UUID NOT NULL, 
    version_number INTEGER NOT NULL, 
    page_number INTEGER NOT NULL, 
    text TEXT NOT NULL, 
    method VARCHAR(30) NOT NULL, 
    confidence FLOAT, 
    blocks JSONB, 
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_ocr_pages PRIMARY KEY (id), 
    CONSTRAINT fk_ocr_pages_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_ocr_pages_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_ocr_pages_document_id_version_number_page_number UNIQUE (document_id, version_number, page_number)
);

CREATE INDEX ix_ocr_pages_document_id ON ocr_pages (document_id);

CREATE INDEX ix_ocr_pages_tenant_id ON ocr_pages (tenant_id);

CREATE TABLE processing_jobs (
    document_id UUID NOT NULL, 
    version_number INTEGER NOT NULL, 
    step VARCHAR(40) NOT NULL, 
    status step_status NOT NULL, 
    attempts INTEGER NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    duration_ms INTEGER, 
    error TEXT, 
    result JSONB, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_processing_jobs PRIMARY KEY (id), 
    CONSTRAINT fk_processing_jobs_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_processing_jobs_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_processing_jobs_document_id_version_number_step UNIQUE (document_id, version_number, step)
);

CREATE INDEX ix_processing_jobs_document_id ON processing_jobs (document_id);

CREATE INDEX ix_processing_jobs_tenant_id ON processing_jobs (tenant_id);

INSERT INTO smartged.alembic_version (version_num) VALUES ('0001') RETURNING smartged.alembic_version.version_num;

-- Running upgrade 0001 -> 0002

ALTER TABLE document_types ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_types FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON document_types USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE folders ENABLE ROW LEVEL SECURITY;

ALTER TABLE folders FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON folders USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE groups ENABLE ROW LEVEL SECURITY;

ALTER TABLE groups FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON groups USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

ALTER TABLE notifications FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON notifications USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE roles ENABLE ROW LEVEL SECURITY;

ALTER TABLE roles FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON roles USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE tenant_modules ENABLE ROW LEVEL SECURITY;

ALTER TABLE tenant_modules FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenant_modules USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE tenant_quotas ENABLE ROW LEVEL SECURITY;

ALTER TABLE tenant_quotas FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenant_quotas USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE tenant_settings ENABLE ROW LEVEL SECURITY;

ALTER TABLE tenant_settings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenant_settings USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE user_tenants ENABLE ROW LEVEL SECURITY;

ALTER TABLE user_tenants FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON user_tenants USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

ALTER TABLE documents FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON documents USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE group_members ENABLE ROW LEVEL SECURITY;

ALTER TABLE group_members FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON group_members USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE metadata_definitions ENABLE ROW LEVEL SECURITY;

ALTER TABLE metadata_definitions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON metadata_definitions USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;

ALTER TABLE role_permissions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON role_permissions USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;

ALTER TABLE user_roles FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON user_roles USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE document_metadata_values ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_metadata_values FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON document_metadata_values USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE document_relations ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_relations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON document_relations USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE document_tags ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_tags FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON document_tags USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_versions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON document_versions USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE ocr_pages ENABLE ROW LEVEL SECURITY;

ALTER TABLE ocr_pages FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON ocr_pages USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE processing_jobs ENABLE ROW LEVEL SECURITY;

ALTER TABLE processing_jobs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON processing_jobs USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON audit_logs USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only';
        END;
        $$ LANGUAGE plpgsql;;

CREATE TRIGGER audit_logs_no_update BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();

UPDATE smartged.alembic_version SET version_num='0002' WHERE smartged.alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

CREATE TYPE view_scope AS ENUM ('tenant', 'personal');

CREATE TABLE document_views (
    scope view_scope NOT NULL, 
    owner_id UUID, 
    name VARCHAR(120) NOT NULL, 
    description VARCHAR(500), 
    icon VARCHAR(40), 
    filters JSONB NOT NULL, 
    is_default BOOLEAN NOT NULL, 
    position INTEGER NOT NULL, 
    created_by UUID, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_document_views PRIMARY KEY (id), 
    CONSTRAINT ck_document_views_owner_matches_scope CHECK ((scope = 'personal') = (owner_id IS NOT NULL)), 
    CONSTRAINT fk_document_views_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT fk_document_views_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_views_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_views_owner ON document_views (tenant_id, owner_id);

CREATE INDEX ix_document_views_tenant_id ON document_views (tenant_id);

CREATE UNIQUE INDEX uq_document_views_tenant_default ON document_views (tenant_id) WHERE scope = 'tenant' AND is_default;

CREATE TABLE object_types (
    code VARCHAR(60) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    description VARCHAR(1000), 
    color VARCHAR(20), 
    icon VARCHAR(40), 
    schema_version INTEGER NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_object_types PRIMARY KEY (id), 
    CONSTRAINT fk_object_types_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_object_types_tenant_id_code UNIQUE (tenant_id, code)
);

CREATE INDEX ix_object_types_tenant_id ON object_types (tenant_id);

CREATE TABLE user_preferences (
    user_id UUID NOT NULL, 
    key VARCHAR(120) NOT NULL, 
    value JSONB NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_user_preferences PRIMARY KEY (id), 
    CONSTRAINT fk_user_preferences_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_user_preferences_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_user_preferences_tenant_id_user_id_key UNIQUE (tenant_id, user_id, key)
);

CREATE INDEX ix_user_preferences_tenant_id ON user_preferences (tenant_id);

CREATE INDEX ix_user_preferences_user_id ON user_preferences (user_id);

CREATE TYPE object_status AS ENUM ('active', 'archived');

CREATE TABLE business_objects (
    object_type_id UUID NOT NULL, 
    code VARCHAR(80) NOT NULL, 
    name VARCHAR(300) NOT NULL, 
    description TEXT, 
    status object_status NOT NULL, 
    attributes JSONB NOT NULL, 
    created_by UUID, 
    search_vector TSVECTOR GENERATED ALWAYS AS (setweight(to_tsvector('simple', coalesce(name, '')), 'A') || setweight(to_tsvector('simple', coalesce(code, '')), 'A') || setweight(to_tsvector('simple', coalesce(description, '')), 'C')) STORED, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_business_objects PRIMARY KEY (id), 
    CONSTRAINT fk_business_objects_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT fk_business_objects_object_type_id_object_types FOREIGN KEY(object_type_id) REFERENCES object_types (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_business_objects_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_business_objects_tenant_id_object_type_id_code UNIQUE (tenant_id, object_type_id, code)
);

CREATE INDEX ix_business_objects_object_type_id ON business_objects (object_type_id);

CREATE INDEX ix_business_objects_search ON business_objects USING gin (search_vector);

CREATE INDEX ix_business_objects_tenant_id ON business_objects (tenant_id);

CREATE TABLE document_object_links (
    document_id UUID NOT NULL, 
    object_id UUID NOT NULL, 
    role VARCHAR(80) NOT NULL, 
    created_by UUID, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_document_object_links PRIMARY KEY (id), 
    CONSTRAINT fk_document_object_links_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT fk_document_object_links_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_object_links_object_id_business_objects FOREIGN KEY(object_id) REFERENCES business_objects (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_object_links_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_document_object_links_document_id_object_id_role UNIQUE (document_id, object_id, role)
);

CREATE INDEX ix_document_object_links_document_id ON document_object_links (document_id);

CREATE INDEX ix_document_object_links_object_id ON document_object_links (object_id);

CREATE INDEX ix_document_object_links_tenant_id ON document_object_links (tenant_id);

ALTER TABLE metadata_definitions ADD COLUMN object_type_id UUID;

ALTER TABLE metadata_definitions ALTER COLUMN document_type_id DROP NOT NULL;

CREATE INDEX ix_metadata_definitions_object_type_id ON metadata_definitions (object_type_id);

ALTER TABLE metadata_definitions ADD CONSTRAINT uq_metadata_definitions_object_type_id_technical_name UNIQUE (object_type_id, technical_name);

ALTER TABLE metadata_definitions ADD CONSTRAINT fk_metadata_definitions_object_type_id_object_types FOREIGN KEY(object_type_id) REFERENCES object_types (id) ON DELETE CASCADE;

ALTER TABLE metadata_definitions ADD CONSTRAINT ck_metadata_definitions_single_owner CHECK ((document_type_id IS NULL) <> (object_type_id IS NULL));

ALTER TABLE document_views ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_views FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON document_views USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

ALTER TABLE user_preferences FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON user_preferences USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE object_types ENABLE ROW LEVEL SECURITY;

ALTER TABLE object_types FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON object_types USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE business_objects ENABLE ROW LEVEL SECURITY;

ALTER TABLE business_objects FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON business_objects USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

ALTER TABLE document_object_links ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_object_links FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON document_object_links USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

UPDATE smartged.alembic_version SET version_num='0003' WHERE smartged.alembic_version.version_num = '0002';

-- Running upgrade 0003 -> 0004

CREATE TABLE ai_model_prices (
    provider_kind VARCHAR(40) NOT NULL, 
    model VARCHAR(120) NOT NULL, 
    input_per_mtok NUMERIC(12, 4) NOT NULL, 
    output_per_mtok NUMERIC(12, 4) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    effective_from TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_ai_model_prices PRIMARY KEY (id), 
    CONSTRAINT uq_ai_model_prices_provider_kind_model_effective_from UNIQUE (provider_kind, model, effective_from)
);

CREATE TABLE ai_prompts (
    tenant_id UUID, 
    code VARCHAR(60) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    description VARCHAR(1000), 
    category VARCHAR(60) NOT NULL, 
    published_version INTEGER, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_ai_prompts PRIMARY KEY (id), 
    CONSTRAINT fk_ai_prompts_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_prompts_tenant_id ON ai_prompts (tenant_id);

CREATE UNIQUE INDEX uq_ai_prompts_global_code ON ai_prompts (code) WHERE tenant_id IS NULL;

CREATE UNIQUE INDEX uq_ai_prompts_tenant_code ON ai_prompts (tenant_id, code) WHERE tenant_id IS NOT NULL;

CREATE TYPE ai_provider_kind AS ENUM ('openai', 'azure_openai', 'anthropic', 'gemini', 'openai_compatible');

CREATE TABLE ai_providers (
    name VARCHAR(120) NOT NULL, 
    kind ai_provider_kind NOT NULL, 
    base_url VARCHAR(500), 
    api_version VARCHAR(40), 
    api_key_encrypted TEXT, 
    api_key_hint VARCHAR(12), 
    default_model VARCHAR(120) NOT NULL, 
    temperature FLOAT, 
    max_tokens INTEGER NOT NULL, 
    timeout_seconds INTEGER NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    is_default BOOLEAN NOT NULL, 
    fallback_provider_id UUID, 
    last_test_at TIMESTAMP WITH TIME ZONE, 
    last_test_ok BOOLEAN, 
    last_test_message VARCHAR(1000), 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_ai_providers PRIMARY KEY (id), 
    CONSTRAINT fk_ai_providers_fallback_provider_id_ai_providers FOREIGN KEY(fallback_provider_id) REFERENCES ai_providers (id) ON DELETE SET NULL, 
    CONSTRAINT fk_ai_providers_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_ai_providers_tenant_id_name UNIQUE (tenant_id, name)
);

CREATE INDEX ix_ai_providers_tenant_id ON ai_providers (tenant_id);

CREATE UNIQUE INDEX uq_ai_providers_tenant_default ON ai_providers (tenant_id) WHERE is_default;

CREATE TABLE ai_usage_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY, 
    tenant_id UUID NOT NULL, 
    idempotency_key VARCHAR(200) NOT NULL, 
    user_id UUID, 
    feature VARCHAR(60) NOT NULL, 
    provider_id UUID, 
    provider_kind VARCHAR(40) NOT NULL, 
    model VARCHAR(120) NOT NULL, 
    prompt_code VARCHAR(60), 
    prompt_version INTEGER, 
    document_id UUID, 
    status VARCHAR(20) NOT NULL, 
    input_tokens INTEGER NOT NULL, 
    output_tokens INTEGER NOT NULL, 
    latency_ms INTEGER, 
    estimated_cost NUMERIC(14, 6), 
    price_id UUID, 
    credits INTEGER NOT NULL, 
    error VARCHAR(1000), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_ai_usage_events PRIMARY KEY (id), 
    CONSTRAINT fk_ai_usage_events_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_ai_usage_events_idempotency_key UNIQUE (idempotency_key)
);

CREATE INDEX ix_ai_usage_tenant_created ON ai_usage_events (tenant_id, created_at);

CREATE TYPE ai_prompt_status AS ENUM ('draft', 'published', 'archived');

CREATE TABLE ai_prompt_versions (
    prompt_id UUID NOT NULL, 
    tenant_id UUID, 
    version INTEGER NOT NULL, 
    status ai_prompt_status NOT NULL, 
    system_prompt TEXT NOT NULL, 
    user_template TEXT NOT NULL, 
    variables JSONB NOT NULL, 
    output_format VARCHAR(20) NOT NULL, 
    model VARCHAR(120), 
    notes VARCHAR(1000), 
    created_by UUID, 
    published_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_ai_prompt_versions PRIMARY KEY (id), 
    CONSTRAINT fk_ai_prompt_versions_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT fk_ai_prompt_versions_prompt_id_ai_prompts FOREIGN KEY(prompt_id) REFERENCES ai_prompts (id) ON DELETE CASCADE, 
    CONSTRAINT fk_ai_prompt_versions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT uq_ai_prompt_versions_prompt_id_version UNIQUE (prompt_id, version)
);

CREATE INDEX ix_ai_prompt_versions_prompt_id ON ai_prompt_versions (prompt_id);

CREATE INDEX ix_ai_prompt_versions_tenant_id ON ai_prompt_versions (tenant_id);

CREATE TABLE ai_prompt_tests (
    prompt_version_id UUID NOT NULL, 
    document_id UUID, 
    provider_id UUID, 
    model VARCHAR(120), 
    output_text TEXT, 
    parsed JSONB, 
    ok BOOLEAN NOT NULL, 
    error TEXT, 
    input_tokens INTEGER, 
    output_tokens INTEGER, 
    latency_ms INTEGER, 
    estimated_cost NUMERIC(14, 6), 
    created_by UUID, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    CONSTRAINT pk_ai_prompt_tests PRIMARY KEY (id), 
    CONSTRAINT fk_ai_prompt_tests_created_by_users FOREIGN KEY(created_by) REFERENCES users (id), 
    CONSTRAINT fk_ai_prompt_tests_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE SET NULL, 
    CONSTRAINT fk_ai_prompt_tests_prompt_version_id_ai_prompt_versions FOREIGN KEY(prompt_version_id) REFERENCES ai_prompt_versions (id) ON DELETE CASCADE, 
    CONSTRAINT fk_ai_prompt_tests_provider_id_ai_providers FOREIGN KEY(provider_id) REFERENCES ai_providers (id) ON DELETE SET NULL, 
    CONSTRAINT fk_ai_prompt_tests_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_prompt_tests_prompt_version_id ON ai_prompt_tests (prompt_version_id);

CREATE INDEX ix_ai_prompt_tests_tenant_id ON ai_prompt_tests (tenant_id);

ALTER TABLE ai_providers ENABLE ROW LEVEL SECURITY;

ALTER TABLE ai_providers FORCE ROW LEVEL SECURITY;

ALTER TABLE ai_prompt_tests ENABLE ROW LEVEL SECURITY;

ALTER TABLE ai_prompt_tests FORCE ROW LEVEL SECURITY;

ALTER TABLE ai_usage_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE ai_usage_events FORCE ROW LEVEL SECURITY;

ALTER TABLE ai_prompts ENABLE ROW LEVEL SECURITY;

ALTER TABLE ai_prompts FORCE ROW LEVEL SECURITY;

ALTER TABLE ai_prompt_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE ai_prompt_versions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON ai_providers USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

CREATE POLICY tenant_isolation ON ai_prompt_tests USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

CREATE POLICY tenant_isolation ON ai_usage_events USING ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

CREATE POLICY tenant_isolation ON ai_prompts USING ((current_setting('app.bypass_rls', true) = 'on') OR tenant_id IS NULL OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

CREATE POLICY tenant_isolation ON ai_prompt_versions USING ((current_setting('app.bypass_rls', true) = 'on') OR tenant_id IS NULL OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), ''))) WITH CHECK ((current_setting('app.bypass_rls', true) = 'on') OR (tenant_id::text = nullif(current_setting('app.tenant_id', true), '')));

UPDATE smartged.alembic_version SET version_num='0004' WHERE smartged.alembic_version.version_num = '0003';


