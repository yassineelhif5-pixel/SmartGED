import { useState } from "react";
import { RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useDocuments, useInvalidateDocs } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { DocumentSummary } from "@/types/api";
import { Card, EmptyState, PageHeader } from "@/components/ui/primitives";
import { ConfirmDialog, DropdownItem } from "@/components/ui/overlay";
import { DocumentTable, Pagination } from "@/features/DocumentTable";

export default function TrashPage() {
  const can = useCan();
  const invalidate = useInvalidateDocs();
  const [page, setPage] = useState(1);
  const [toPurge, setToPurge] = useState<DocumentSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const { data, isLoading } = useDocuments({ trashed: true, sort: "updated_at", order: "desc", page, page_size: 25 });

  const restore = async (d: DocumentSummary) => {
    try {
      await api(`/documents/${d.id}/restore`, { method: "POST" });
      toast.success(`« ${d.title} » restauré`);
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const purge = async () => {
    if (!toPurge) return;
    setBusy(true);
    try {
      await api(`/documents/${toPurge.id}/purge`, { method: "DELETE" });
      toast.success("Document supprimé définitivement");
      setToPurge(null);
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Corbeille" description="Les documents supprimés restent récupérables jusqu'à leur purge définitive par un administrateur." />
      <Card>
        {data?.total === 0 ? (
          <EmptyState icon={Trash2} title="La corbeille est vide" />
        ) : (
          <>
            <DocumentTable items={data?.items} loading={isLoading} sort="updated_at" order="desc" onSort={() => {}} showDeleted
              rowActions={(d) => (
                <>
                  <DropdownItem onSelect={() => restore(d)}><RotateCcw /> Restaurer</DropdownItem>
                  {can("tenant_settings:administer") && (
                    <DropdownItem destructive onSelect={() => setToPurge(d)}><Trash2 /> Supprimer définitivement</DropdownItem>
                  )}
                </>
              )} />
            {data && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
          </>
        )}
      </Card>
      <ConfirmDialog open={!!toPurge} onOpenChange={(o) => !o && setToPurge(null)} destructive loading={busy}
                     title="Suppression définitive" confirmLabel="Supprimer définitivement" onConfirm={purge}
                     description={`« ${toPurge?.title} » et toutes ses versions seront effacés du stockage. Cette action est irréversible et tracée dans le journal d'audit.`} />
    </>
  );
}
