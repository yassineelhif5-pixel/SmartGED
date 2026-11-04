import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, ShieldAlert, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api, downloadFile } from "@/api/client";
import { useAudit } from "@/hooks/queries";
import { Badge, Button, Card, Input, PageHeader } from "@/components/ui/primitives";
import { Pagination } from "@/features/DocumentTable";
import { formatDateTime } from "@/utils/format";

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const { data } = useAudit({ action: action || undefined, page, page_size: 50 });
  const verify = useQuery({ queryKey: ["audit-verify"], queryFn: () => api<{ valid: boolean; checked: number }>("/audit/verify") });

  return (
    <>
      <PageHeader title="Journal d'audit"
                  description="Trace inaltérable de toutes les opérations sensibles. Chaque entrée est chaînée cryptographiquement à la précédente."
                  actions={<Button variant="outline" onClick={() => downloadFile("/audit/export.csv", "audit-log.csv", { action: action || undefined }).catch((e) => toast.error(e.message))}><Download /> Export CSV</Button>} />
      {verify.data && (
        <div className={`mb-4 flex items-center gap-3 rounded-lg border px-4 py-3 text-sm ${verify.data.valid ? "border-success/30 bg-success/5" : "border-destructive/30 bg-destructive/5"}`}>
          {verify.data.valid ? <ShieldCheck className="size-5 text-success" /> : <ShieldAlert className="size-5 text-destructive" />}
          {verify.data.valid
            ? `Intégrité vérifiée : ${verify.data.checked} entrées, chaîne de hachage intacte.`
            : "Rupture détectée dans la chaîne d'audit — contactez votre administrateur sécurité."}
        </div>
      )}
      <Card>
        <div className="border-b p-3">
          <Input className="max-w-xs" placeholder="Filtrer par action (ex. document., auth.login)" value={action}
                 onChange={(e) => { setAction(e.target.value); setPage(1); }} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">Date</th>
                <th className="px-4 py-2.5 text-left font-medium">Action</th>
                <th className="px-4 py-2.5 text-left font-medium">Acteur</th>
                <th className="hidden px-4 py-2.5 text-left font-medium lg:table-cell">Ressource</th>
                <th className="hidden px-4 py-2.5 text-left font-medium md:table-cell">IP</th>
                <th className="hidden px-4 py-2.5 text-left font-medium xl:table-cell">Détails</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data?.items.map((e) => (
                <tr key={e.id}>
                  <td className="tabular whitespace-nowrap px-4 py-2.5 text-muted-foreground">{formatDateTime(e.created_at)}</td>
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-xs">{e.action}</span>
                    {e.outcome !== "success" && <Badge tone="red" className="ml-2">{e.outcome}</Badge>}
                  </td>
                  <td className="px-4 py-2.5">{e.actor_email ?? "système"}</td>
                  <td className="hidden px-4 py-2.5 font-mono text-xs text-muted-foreground lg:table-cell">{e.resource_type}{e.resource_id && ` · ${e.resource_id.slice(0, 8)}`}</td>
                  <td className="hidden px-4 py-2.5 text-muted-foreground md:table-cell">{e.ip_address ?? "—"}</td>
                  <td className="hidden max-w-[320px] truncate px-4 py-2.5 font-mono text-[11px] text-muted-foreground xl:table-cell" title={JSON.stringify(e.details)}>
                    {e.details ? JSON.stringify(e.details) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      </Card>
    </>
  );
}
