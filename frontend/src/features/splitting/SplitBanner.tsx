import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileStack, Scissors } from "lucide-react";
import { api } from "@/api/client";
import type { DocumentDetail, DocumentSummary, SplitState } from "@/types/api";
import { Button } from "@/components/ui/primitives";

/** Split context on the viewer: pending proposal, split parent, or child of a split batch. */
export function SplitBanner({ doc }: { doc: DocumentDetail }) {
  const relevant = doc.mime_type === "application/pdf" && (doc.page_count ?? 0) > 1 && !doc.parent_document_id;
  const { data: state } = useQuery({
    queryKey: ["split", doc.id, doc.status], queryFn: () => api<SplitState>(`/documents/${doc.id}/split`), enabled: relevant,
  });
  const { data: parent } = useQuery({
    queryKey: ["document", doc.parent_document_id], enabled: !!doc.parent_document_id,
    queryFn: () => api<DocumentSummary>(`/documents/${doc.parent_document_id}`),
  });

  if (doc.parent_document_id)
    return (
      <div className="mb-3 flex items-center gap-2 rounded-lg border bg-muted/40 px-4 py-2 text-sm">
        <FileStack className="size-4 text-muted-foreground" />
        Extrait du lot <Link className="font-medium text-primary hover:underline" to={`/documents/${doc.parent_document_id}`}>« {parent?.title ?? "document d'origine"} »</Link>
      </div>
    );
  const p = state?.proposal;
  if (p?.status === "proposed")
    return (
      <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-2 text-sm">
        <Scissors className="size-4 text-warning" />
        <span>
          Ce PDF semble contenir <strong>{p.segments.length} documents</strong>
          {p.method === "ai" ? " (détection IA)" : " (analyse de structure)"} — la classification attend votre vérification.
        </span>
        <Button asChild size="sm" className="ml-auto h-7"><Link to={`/documents/${doc.id}/split`}>Vérifier le découpage</Link></Button>
      </div>
    );
  if (p?.status === "applied")
    return (
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-4 py-2 text-sm">
        <FileStack className="size-4 text-muted-foreground" />
        Lot découpé en {p.child_document_ids.length} documents (onglet « Relations »). L'original est archivé pour traçabilité.
        <Link className="ml-auto text-xs font-medium text-primary hover:underline" to={`/documents/${doc.id}/split`}>Détail du découpage</Link>
      </div>
    );
  return null;
}
