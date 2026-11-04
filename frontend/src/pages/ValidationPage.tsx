import { useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { useDocuments } from "@/hooks/queries";
import { Card, EmptyState, PageHeader } from "@/components/ui/primitives";
import { DocumentTable, Pagination } from "@/features/DocumentTable";

export default function ValidationPage() {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const { data, isLoading } = useDocuments({ status: "pending_validation", sort, order, page, page_size: 25 });
  return (
    <>
      <PageHeader title="Centre de validation"
                  description="Documents dont les métadonnées obligatoires ou sensibles doivent être confirmées par un humain avant publication." />
      <Card>
        {data?.total === 0 ? (
          <EmptyState icon={ClipboardCheck} title="Rien à valider" description="Tous les documents ont été traités." />
        ) : (
          <>
            <DocumentTable items={data?.items} loading={isLoading} sort={sort} order={order}
                           onSort={(f) => { setOrder(sort === f && order === "desc" ? "asc" : "desc"); setSort(f); }} />
            {data && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
          </>
        )}
      </Card>
    </>
  );
}
