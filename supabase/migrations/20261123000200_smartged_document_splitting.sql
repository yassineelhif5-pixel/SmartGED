CREATE SCHEMA IF NOT EXISTS smartged;
SET search_path TO smartged, public;
-- Running upgrade 0005 -> 0006
CREATE TYPE split_status AS ENUM ('proposed', 'applied', 'dismissed', 'superseded');
CREATE TABLE document_split_proposals (
    id UUID NOT NULL, 
    tenant_id UUID NOT NULL, 
    document_id UUID NOT NULL, 
    version_number INTEGER NOT NULL, 
    status split_status NOT NULL, 
    method VARCHAR(20) NOT NULL, 
    page_count INTEGER NOT NULL, 
    segments JSONB NOT NULL, 
    separator_pages JSONB NOT NULL, 
    confidence FLOAT, 
    details JSONB NOT NULL, 
    decided_by UUID, 
    decided_at TIMESTAMP WITH TIME ZONE, 
    child_document_ids JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_document_split_proposals PRIMARY KEY (id), 
    CONSTRAINT fk_document_split_proposals_decided_by_users FOREIGN KEY(decided_by) REFERENCES users (id), 
    CONSTRAINT fk_document_split_proposals_document_id_documents FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    CONSTRAINT fk_document_split_proposals_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);
CREATE INDEX ix_document_split_proposals_document ON document_split_proposals (document_id, status);
CREATE INDEX ix_document_split_proposals_decided_by_fk ON document_split_proposals (decided_by);
CREATE INDEX ix_document_split_proposals_tenant_id ON document_split_proposals (tenant_id);
ALTER TABLE document_split_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_split_proposals FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON document_split_proposals USING (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid))) WITH CHECK (((select current_setting('app.bypass_rls', true)) = 'on') OR (tenant_id = (select nullif(current_setting('app.tenant_id', true), '')::uuid)));
UPDATE smartged.alembic_version SET version_num='0006' WHERE smartged.alembic_version.version_num = '0005';
GRANT SELECT, INSERT, UPDATE, DELETE ON smartged.document_split_proposals TO smartged_app;
