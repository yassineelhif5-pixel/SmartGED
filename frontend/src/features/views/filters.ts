/** Conversion between the document explorer URL and a saved view's filters. */
import type { DocumentFilters } from "@/types/api";

export const FILTER_PARAMS = ["q", "folder", "type", "status", "tag", "mine", "object", "from", "to", "meta", "sort", "order"];

export function filtersFromParams(params: URLSearchParams): DocumentFilters {
  const meta: Record<string, string> = {};
  params.getAll("meta").forEach((m) => {
    const i = m.indexOf(":");
    if (i > 0) meta[m.slice(0, i)] = m.slice(i + 1);
  });
  const q = params.get("q") || null;
  return {
    q,
    folder_id: params.get("folder"),
    recursive: true,
    document_type_id: params.get("type"),
    status: (params.get("status") as DocumentFilters["status"]) || null,
    tag: params.get("tag"),
    mine: params.get("mine") === "1",
    object_id: params.get("object"),
    created_from: params.get("from"),
    created_to: params.get("to"),
    meta,
    sort: params.get("sort") ?? (q ? "relevance" : "created_at"),
    order: (params.get("order") as "asc" | "desc") ?? "desc",
  };
}

export function paramsFromFilters(f: DocumentFilters, viewId?: string | null): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.folder_id) p.set("folder", f.folder_id);
  if (f.document_type_id) p.set("type", f.document_type_id);
  if (f.status) p.set("status", f.status);
  if (f.tag) p.set("tag", f.tag);
  if (f.mine) p.set("mine", "1");
  if (f.object_id) p.set("object", f.object_id);
  if (f.created_from) p.set("from", f.created_from);
  if (f.created_to) p.set("to", f.created_to);
  Object.entries(f.meta ?? {}).forEach(([k, v]) => v && p.append("meta", `${k}:${v}`));
  if (f.sort && f.sort !== (f.q ? "relevance" : "created_at")) p.set("sort", f.sort);
  if (f.order && f.order !== "desc") p.set("order", f.order);
  if (viewId) p.set("view", viewId);
  return p;
}

/** Stable comparison used to detect "this view has unsaved changes". */
export function sameFilters(a: DocumentFilters, b: DocumentFilters): boolean {
  return paramsFromFilters(a).toString() === paramsFromFilters(b).toString();
}

export function hasActiveFilters(params: URLSearchParams): boolean {
  return FILTER_PARAMS.some((k) => params.has(k));
}

export function countFilters(f: DocumentFilters): number {
  return [f.document_type_id, f.status, f.tag, f.mine, f.object_id, f.created_from, f.created_to].filter(Boolean).length +
    Object.keys(f.meta ?? {}).length;
}
