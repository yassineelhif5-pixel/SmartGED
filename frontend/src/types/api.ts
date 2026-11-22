export type UUID = string;

export type StepStatus = "pending" | "running" | "completed" | "failed" | "skipped" | "not_configured";
export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "pending_validation"
  | "published"
  | "rejected"
  | "archived"
  | "failed";
export type DataType =
  | "text"
  | "long_text"
  | "integer"
  | "decimal"
  | "currency"
  | "date"
  | "datetime"
  | "boolean"
  | "dropdown"
  | "multi_select"
  | "reference"
  | "calculated";

export interface TenantBrief {
  id: UUID;
  slug: string;
  name: string;
  status: string;
}

export interface User {
  id: UUID;
  email: string;
  full_name: string;
  platform_role: "super_admin" | "support_admin" | "auditor" | null;
  is_active: boolean;
  locale: string;
  last_login_at: string | null;
}

export interface Session {
  access_token: string;
  expires_in: number;
  user: User;
  tenant: TenantBrief | null;
  tenants: TenantBrief[];
  permissions: string[];
  platform_capabilities: string[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Folder {
  id: UUID;
  parent_id: UUID | null;
  name: string;
  description: string | null;
  created_at: string;
  document_count: number;
}

export interface MetadataField {
  id?: UUID;
  technical_name: string;
  display_name: string;
  description?: string | null;
  data_type: DataType;
  required: boolean;
  default_value?: unknown;
  validation_rules: Record<string, unknown>;
  allowed_values?: string[] | null;
  searchable: boolean;
  visible: boolean;
  ai_extraction_enabled: boolean;
  extraction_prompt?: string | null;
  sensitive: boolean;
  requires_human_validation: boolean;
  position?: number;
}

export interface DocumentType {
  id: UUID;
  code: string;
  name: string;
  description: string | null;
  color: string | null;
  icon: string | null;
  schema_version: number;
  requires_validation: boolean;
  classification_hints: string | null;
  is_active: boolean;
  fields: MetadataField[];
  document_count: number;
}

export interface DocumentSummary {
  id: UUID;
  title: string;
  file_name: string;
  original_file_name: string;
  mime_type: string;
  extension: string;
  file_size: number;
  sha256: string;
  page_count: number | null;
  folder_id: UUID | null;
  parent_document_id: UUID | null;
  document_type: { id: UUID; code: string; name: string; color: string | null; icon: string | null } | null;
  current_version: number;
  owner_id: UUID | null;
  status: DocumentStatus;
  language: string | null;
  scan_status: StepStatus;
  ocr_status: StepStatus;
  ai_status: StepStatus;
  classification_status: StepStatus;
  validation_status: StepStatus;
  classification_confidence: number | null;
  duplicate_of_id: UUID | null;
  checked_out_by: UUID | null;
  checked_out_at: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  tags: string[];
}

export interface MetadataValue {
  definition_id: UUID;
  technical_name: string;
  display_name: string;
  data_type: DataType;
  value: unknown;
  source: string;
  confidence: number | null;
  source_page: number | null;
  source_text: string | null;
  validation_status: StepStatus;
  validated_at: string | null;
  sensitive: boolean;
  required: boolean;
  display_value?: string | null;
  reference_type?: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  metadata: MetadataValue[];
  owner_name: string | null;
  checked_out_by_name: string | null;
}

export interface Version {
  id: UUID;
  version_number: number;
  author_id: UUID | null;
  comment: string | null;
  change_reason: string | null;
  file_name: string;
  mime_type: string;
  file_size: number;
  sha256: string;
  created_at: string;
}

export interface OcrPage {
  page_number: number;
  text: string;
  method: string;
  confidence: number | null;
}

export interface Job {
  id: UUID;
  document_id: UUID;
  version_number: number;
  step: string;
  status: StepStatus;
  attempts: number;
  duration_ms: number | null;
  error: string | null;
  result: Record<string, unknown> | null;
  started_at?: string | null;
  finished_at?: string | null;
  updated_at?: string;
  document_title?: string;
}

export interface Role {
  id: UUID;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permissions: string[];
}

export interface Member {
  user: User;
  status: "invited" | "active" | "disabled";
  department: string | null;
  job_title: string | null;
  roles: { id: UUID; code: string; name: string }[];
  joined_at: string;
}

export interface AuditEntry {
  id: number;
  created_at: string;
  action: string;
  actor_email: string | null;
  actor_user_id: UUID | null;
  resource_type: string | null;
  resource_id: string | null;
  outcome: string;
  ip_address: string | null;
  details: Record<string, unknown> | null;
}

export interface Plan {
  id: UUID;
  code: string;
  name: string;
  max_users: number;
  max_storage_bytes: number;
  monthly_ai_credits: number;
  modules: string[];
}

export interface TenantDetail {
  id: UUID;
  slug: string;
  name: string;
  status: "provisioning" | "active" | "suspended" | "archived";
  storage_provider: string;
  created_at: string;
  suspended_at: string | null;
  plan: Plan | null;
  usage?: Record<string, number>;
  quotas?: Record<string, number>;
  modules?: string[];
}

export interface DashboardStats {
  documents_total: number;
  by_status: Record<DocumentStatus, number>;
  by_type: { name: string; color: string; count: number }[];
  uploads_last_30_days: { date: string; uploads: number }[];
  storage_bytes: number;
  storage_quota_bytes: number | null;
  users: number;
  users_quota: number | null;
  ocr_avg_ms: number | null;
  failed_jobs: number;
  pending_validation: number;
}

export interface DocumentFilters {
  q?: string | null;
  folder_id?: UUID | null;
  recursive?: boolean;
  document_type_id?: UUID | null;
  status?: DocumentStatus | null;
  tag?: string | null;
  mine?: boolean;
  object_id?: UUID | null;
  created_from?: string | null;
  created_to?: string | null;
  meta?: Record<string, string>;
  sort?: string;
  order?: "asc" | "desc";
}

export interface DocumentView {
  id: UUID;
  name: string;
  description: string | null;
  icon: string | null;
  scope: "tenant" | "personal";
  filters: DocumentFilters;
  is_default: boolean;
  position: number;
  is_mine: boolean;
  can_edit: boolean;
}

export interface ViewsResponse {
  views: DocumentView[];
  default_view_id: UUID | null;
  default_source: "user" | "tenant" | "none";
}

export interface ObjectType {
  id: UUID;
  code: string;
  name: string;
  description: string | null;
  color: string | null;
  icon: string | null;
  schema_version: number;
  is_active: boolean;
  fields: MetadataField[];
  object_count: number;
}

export interface BusinessObject {
  id: UUID;
  object_type: { id: UUID; code: string; name: string; color: string | null; icon: string | null };
  code: string;
  name: string;
  description: string | null;
  status: "active" | "archived";
  attributes: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  document_count: number;
}

export interface ObjectLink {
  id: UUID;
  role: string;
  object: BusinessObject;
}
