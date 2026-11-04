import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Cpu } from "lucide-react";
import { api } from "@/api/client";
import type { Job, StepStatus } from "@/types/api";
import { Card, EmptyState, PageHeader, Select, Skeleton } from "@/components/ui/primitives";
import { STEP_LABELS, StepBadge } from "@/components/StatusBadge";
import { Pagination } from "@/features/DocumentTable";
import { timeAgo } from "@/utils/format";

interface JobsResponse {
  items: Job[];
  total: number;
  page: number;
  page_size: number;
  summary: Record<StepStatus, number>;
}

export default function ProcessingPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const step = params.get("step") ?? "";
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({
    queryKey: ["jobs", status, step, page],
    queryFn: () => api<JobsResponse>("/processing/jobs", { query: { status, step, page, page_size: 50 } }),
    refetchInterval: 5000,
  });
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(params);
    if (v) n.set(k, v);
    else n.delete(k);
    setParams(n, { replace: true });
    setPage(1);
  };

  return (
    <>
      <PageHeader title="Centre de traitement" description="Suivi en temps réel du pipeline documentaire : antivirus, OCR, langue, IA, indexation." />
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {(["running", "pending", "completed", "failed", "not_configured", "skipped"] as StepStatus[]).map((s) => (
          <button key={s} onClick={() => set("status", status === s ? "" : s)}
                  className={`rounded-lg border bg-card p-3 text-left shadow-card transition ${status === s ? "ring-2 ring-ring" : "hover:bg-muted/40"}`}>
            <StepBadge status={s} />
            <div className="tabular mt-2 text-xl font-semibold">{data?.summary[s] ?? "—"}</div>
          </button>
        ))}
      </div>
      <Card>
        <div className="flex gap-2 border-b p-3">
          <Select className="w-auto" value={step} onChange={(e) => set("step", e.target.value)} aria-label="Étape">
            <option value="">Toutes les étapes</option>
            {Object.entries(STEP_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </div>
        {isLoading ? (
          <div className="space-y-2 p-4">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-8" />)}</div>
        ) : data?.items.length === 0 ? (
          <EmptyState icon={Cpu} title="Aucune étape" description="Aucun traitement ne correspond à ces filtres." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium">Document</th>
                  <th className="px-4 py-2.5 text-left font-medium">Étape</th>
                  <th className="px-4 py-2.5 text-left font-medium">Statut</th>
                  <th className="hidden px-4 py-2.5 text-left font-medium md:table-cell">Durée</th>
                  <th className="hidden px-4 py-2.5 text-left font-medium md:table-cell">Détail</th>
                  <th className="px-4 py-2.5 text-right font-medium">Mis à jour</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {data?.items.map((j) => (
                  <tr key={j.id} className="hover:bg-muted/40">
                    <td className="max-w-[240px] truncate px-4 py-2.5">
                      <Link to={`/documents/${j.document_id}`} className="font-medium hover:text-primary">{j.document_title}</Link>
                      <span className="text-xs text-muted-foreground"> · v{j.version_number}</span>
                    </td>
                    <td className="px-4 py-2.5">{STEP_LABELS[j.step] ?? j.step}</td>
                    <td className="px-4 py-2.5"><StepBadge status={j.status} /></td>
                    <td className="tabular hidden px-4 py-2.5 text-muted-foreground md:table-cell">{j.duration_ms !== null ? `${j.duration_ms} ms` : "—"}</td>
                    <td className="hidden max-w-[320px] truncate px-4 py-2.5 text-xs text-muted-foreground md:table-cell" title={j.error ?? undefined}>
                      {j.error ? j.error.split("\n")[0] : j.result && "reason" in j.result ? String(j.result.reason) : ""}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-muted-foreground">{j.updated_at ? timeAgo(j.updated_at) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      </Card>
    </>
  );
}
