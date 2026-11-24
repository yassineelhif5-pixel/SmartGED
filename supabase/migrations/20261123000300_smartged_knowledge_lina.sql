CREATE SCHEMA IF NOT EXISTS smartged;
SET search_path TO smartged, public, extensions;
-- Running upgrade 0006 -> 0007
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
ALTER TABLE ai_providers ADD COLUMN embedding_model VARCHAR(120);
CREATE TABLE document_chunks (
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    document_id UUID NOT NULL, 
    version_number INTEGER NOT NULL, 
    chunk_index INTEGER NOT NULL, 
    page_from INTEGER, 
    page_to INTEGER, 
    text TEXT NOT NULL, 
    char_count INTEGER NOT NULL, 
    embedding VECTOR, 
    embedding_model VARCHAR(160), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text, ''))) STORED, 
    CONSTRAINT pk_document_chunks PRIMARY KEY (id), 
    CONSTRAINT fk_document_chunks_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_chunks_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);
CREATE INDEX ix_document_chunks_document ON document_chunks (document_id, version_number, chunk_index);
CREATE INDEX ix_document_chunks_search ON document_chunks USING gin (search_vector);
CREATE INDEX ix_document_chunks_tenant_id ON document_chunks (tenant_id);
CREATE TABLE lina_conversations (
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    scope JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_lina_conversations PRIMARY KEY (id), 
    CONSTRAINT fk_lina_conversations_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
    CONSTRAINT fk_lina_conversations_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX ix_lina_conversations_user ON lina_conversations (tenant_id, user_id);
CREATE INDEX ix_lina_conversations_user_id_fk ON lina_conversations (user_id);
CREATE INDEX ix_lina_conversations_tenant_id ON lina_conversations (tenant_id);
CREATE TABLE lina_messages (
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    content TEXT NOT NULL, 
    citations JSONB NOT NULL, 
    meta JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_lina_messages PRIMARY KEY (id), 
    CONSTRAINT fk_lina_messages_conversation_id_lina_conversations FOREIGN KEY(conversation_id) REFERENCES lina_conversations (id) ON DELETE CASCADE, 
    CONSTRAINT fk_lina_messages_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);
CREATE INDEX ix_lina_messages_conversation ON lina_messages (conversation_id, created_at);
CREATE INDEX ix_lina_messages_tenant_id ON lina_messages (tenant_id);
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON document_chunks USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));
ALTER TABLE lina_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE lina_conversations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON lina_conversations USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));
ALTER TABLE lina_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE lina_messages FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON lina_messages USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));
UPDATE smartged.alembic_version SET version_num='0007' WHERE smartged.alembic_version.version_num = '0006';
GRANT SELECT, INSERT, UPDATE, DELETE ON smartged.document_chunks, smartged.lina_conversations, smartged.lina_messages TO smartged_app;
GRANT USAGE ON SCHEMA extensions TO smartged_app;
