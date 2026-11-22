/** TanStack Query hooks — one place for every server-state access. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  AuditEntry,
  BusinessObject,
  ObjectLink,
  ObjectType,
  ViewsResponse,
  DashboardStats,
  DocumentDetail,
  DocumentSummary,
  DocumentType,
  Folder,
  Job,
  Member,
  OcrPage,
  Page,
  Role,
  Version,
} from "@/types/api";

export const qk = {
  folders: ["folders"] as const,
  types: ["document-types"] as const,
  documents: (params: object) => ["documents", params] as const,
  document: (id: string) => ["document", id] as const,
  dashboard: ["dashboard"] as const,
};

export const useFolders = () => useQuery({ queryKey: qk.folders, queryFn: () => api<Folder[]>("/folders") });
export const useDocumentTypes = () =>
  useQuery({ queryKey: qk.types, queryFn: () => api<DocumentType[]>("/document-types") });
export const useDashboard = () =>
  useQuery({ queryKey: qk.dashboard, queryFn: () => api<DashboardStats>("/dashboard"), refetchInterval: 30_000 });

export interface DocumentQuery {
  q?: string;
  folder_id?: string;
  recursive?: boolean;
  document_type_id?: string;
  status?: string;
  tag?: string;
  trashed?: boolean;
  mine?: boolean;
  object_id?: string;
  created_from?: string;
  created_to?: string;
  meta?: string[];
  sort?: string;
  order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export function useDocuments(params: DocumentQuery) {
  return useQuery({
    queryKey: qk.documents(params),
    queryFn: () => api<Page<DocumentSummary>>("/documents", { query: params as Record<string, unknown> }),
    placeholderData: (prev) => prev,
    // keep polling while something is being processed so the UI reflects real progress
    refetchInterval: (q) =>
      q.state.data?.items.some((d) => d.status === "processing" || d.status === "uploaded") ? 2500 : false,
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: qk.document(id),
    queryFn: () => api<DocumentDetail>(`/documents/${id}`),
    refetchInterval: (q) =>
      q.state.data && ["processing", "uploaded"].includes(q.state.data.status) ? 2000 : false,
  });
}

export const useVersions = (id: string) =>
  useQuery({ queryKey: ["versions", id], queryFn: () => api<Version[]>(`/documents/${id}/versions`) });
export const usePages = (id: string, version: number, enabled = true) =>
  useQuery({ queryKey: ["pages", id, version], queryFn: () => api<OcrPage[]>(`/documents/${id}/pages`), enabled });
export const useJobs = (id: string, active: boolean) =>
  useQuery({
    queryKey: ["jobs", id],
    queryFn: () => api<Job[]>(`/documents/${id}/jobs`),
    refetchInterval: active ? 1500 : false,
  });
export const useRelations = (id: string) =>
  useQuery({
    queryKey: ["relations", id],
    queryFn: () => api<{ id: string; relation_type: string; direction: string; document: DocumentSummary }[]>(
      `/documents/${id}/relations`,
    ),
  });

export const useMembers = () => useQuery({ queryKey: ["members"], queryFn: () => api<Member[]>("/users") });
export const useRoles = () => useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles") });
export const useAudit = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ["audit", params],
    queryFn: () => api<Page<AuditEntry>>("/audit", { query: params }),
    placeholderData: (prev) => prev,
  });

/** Invalidate everything document-related after a mutation. */
export function useInvalidateDocs() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["documents"] });
    qc.invalidateQueries({ queryKey: ["document"] });
    qc.invalidateQueries({ queryKey: qk.folders });
    qc.invalidateQueries({ queryKey: qk.dashboard });
  };
}

export function useApiMutation<TVars, TRes = unknown>(fn: (v: TVars) => Promise<TRes>, onSuccess?: (r: TRes) => void) {
  return useMutation({ mutationFn: fn, onSuccess });
}

export const useViews = () =>
  useQuery({ queryKey: ["document-views"], queryFn: () => api<ViewsResponse>("/document-views") });
export const useObjectTypes = () =>
  useQuery({ queryKey: ["object-types"], queryFn: () => api<ObjectType[]>("/object-types") });
export function useObjects(params: { object_type_id?: string; type_code?: string; q?: string; status?: string; page?: number; page_size?: number }, enabled = true) {
  return useQuery({
    queryKey: ["objects", params],
    queryFn: () => api<Page<BusinessObject>>("/objects", { query: params }),
    placeholderData: (prev) => prev,
    enabled,
  });
}
export const useDocumentObjects = (id: string) =>
  useQuery({ queryKey: ["document-objects", id], queryFn: () => api<ObjectLink[]>(`/documents/${id}/objects`) });
