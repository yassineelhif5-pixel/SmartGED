import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, Copy, FileImage, FileSpreadsheet, FileText, Lock, MoreHorizontal } from "lucide-react";
import type { DocumentSummary } from "@/types/api";
import { cn, formatBytes, formatDateTime } from "@/utils/format";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { DocumentStatusBadge } from "@/components/StatusBadge";
import { DropdownContent, DropdownMenu, DropdownTrigger } from "@/components/ui/overlay";

export function fileIcon(mime: string) {
  if (mime.startsWith("image/")) return FileImage;
  if (mime.includes("spreadsheet") || mime === "text/csv") return FileSpreadsheet;
  return FileText;
}

interface Props {
  items: DocumentSummary[] | undefined;
  loading: boolean;
  sort: string;
  order: "asc" | "desc";
  onSort: (field: string) => void;
  rowActions?: (d: DocumentSummary) => React.ReactNode;
  showDeleted?: boolean;
}

function SortHeader({ label, field, sort, order, onSort, className }: {
  label: string; field: string; sort: string; order: string; onSort: (f: string) => void; className?: string;
}) {
  const active = sort === field;
  return (
    <th className={cn("px-4 py-2.5 text-left font-medium", className)}>
      <button className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => onSort(field)}>
        {label}
        {active && (order === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
      </button>
    </th>
  );
}

export function DocumentTable({ items, loading, sort, order, onSort, rowActions, showDeleted }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
          <tr>
            <SortHeader label="Document" field="title" sort={sort} order={order} onSort={onSort} className="w-[45%]" />
            <th className="hidden px-4 py-2.5 text-left font-medium lg:table-cell">Type</th>
            <SortHeader label="Statut" field="status" sort={sort} order={order} onSort={onSort} />
            <SortHeader label="Taille" field="file_size" sort={sort} order={order} onSort={onSort} className="hidden md:table-cell" />
            <SortHeader label={showDeleted ? "Modifié" : "Déposé le"} field={showDeleted ? "updated_at" : "created_at"} sort={sort} order={order} onSort={onSort} className="hidden md:table-cell" />
            <th className="w-10" />
          </tr>
        </thead>
        <tbody className="divide-y">
          {loading &&
            !items &&
            Array.from({ length: 6 }).map((_, i) => (
              <tr key={i}>
                <td colSpan={6} className="px-4 py-3"><Skeleton className="h-5" /></td>
              </tr>
            ))}
          {items?.map((d) => {
            const Icon = fileIcon(d.mime_type);
            return (
              <tr key={d.id} className="group hover:bg-muted/40">
                <td className="max-w-0 px-4 py-2.5">
                  <Link to={`/documents/${d.id}`} className="flex items-center gap-3">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-accent">
                      <Icon className="size-4 text-accent-foreground" />
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5">
                        <span className="truncate font-medium group-hover:text-primary">{d.title}</span>
                        {d.checked_out_by && <Lock className="size-3 shrink-0 text-warning" aria-label="Extrait (check-out)" />}
                        {d.duplicate_of_id && <Copy className="size-3 shrink-0 text-muted-foreground" aria-label="Doublon" />}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {d.original_file_name} · v{d.current_version}
                        {d.tags.length > 0 && ` · ${d.tags.map((t) => `#${t}`).join(" ")}`}
                      </span>
                    </span>
                  </Link>
                </td>
                <td className="hidden px-4 py-2.5 lg:table-cell">
                  {d.document_type ? (
                    <Badge tone="outline">
                      <span className="size-2 rounded-full" style={{ background: d.document_type.color ?? "#94a3b8" }} />
                      {d.document_type.name}
                    </Badge>
                  ) : (
                    <span className="text-xs text-muted-foreground">Non classé</span>
                  )}
                </td>
                <td className="px-4 py-2.5"><DocumentStatusBadge status={d.status} /></td>
                <td className="tabular hidden whitespace-nowrap px-4 py-2.5 text-muted-foreground md:table-cell">{formatBytes(d.file_size)}</td>
                <td className="hidden whitespace-nowrap px-4 py-2.5 text-muted-foreground md:table-cell">
                  {formatDateTime(showDeleted ? d.deleted_at : d.created_at)}
                </td>
                <td className="px-2 py-2.5 text-right">
                  {rowActions && (
                    <DropdownMenu>
                      <DropdownTrigger asChild>
                        <button className="rounded p-1 text-muted-foreground hover:bg-muted" aria-label="Actions">
                          <MoreHorizontal className="size-4" />
                        </button>
                      </DropdownTrigger>
                      <DropdownContent>{rowActions(d)}</DropdownContent>
                    </DropdownMenu>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between border-t px-4 py-3 text-xs text-muted-foreground">
      <span className="tabular">
        {total === 0 ? "0 résultat" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} sur ${total}`}
      </span>
      <div className="flex gap-1">
        <button className="rounded border px-2.5 py-1 hover:bg-muted disabled:opacity-40" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Précédent
        </button>
        <button className="rounded border px-2.5 py-1 hover:bg-muted disabled:opacity-40" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Suivant
        </button>
      </div>
    </div>
  );
}
