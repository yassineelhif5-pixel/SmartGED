import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, ClipboardCheck, FileText, HardDrive, Timer, Upload, Users } from "lucide-react";
import { useDashboard, useDocuments } from "@/hooks/queries";
import { useSessionStore } from "@/stores/session";
import { Button, Card, CardHeader, PageHeader, Skeleton } from "@/components/ui/primitives";
import { DocumentStatusBadge } from "@/components/StatusBadge";
import { formatBytes, timeAgo } from "@/utils/format";

function Kpi({
  icon: Icon,
  label,
  value,
  sub,
  to,
}: {
  icon: typeof FileText;
  label: string;
  value: string | number;
  sub?: string;
  to?: string;
}) {
  const body = (
    <Card className="p-5 transition-shadow hover:shadow-md">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        <Icon className="size-4 text-muted-foreground" />
      </div>
      <div className="tabular mt-3 text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </Card>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export default function DashboardPage() {
  const user = useSessionStore((s) => s.session?.user);
  const { data, isLoading } = useDashboard();
  const recent = useDocuments({ page_size: 6, sort: "created_at", order: "desc" });

  const storagePct =
    data?.storage_quota_bytes ? Math.min(100, (data.storage_bytes / data.storage_quota_bytes) * 100) : null;

  return (
    <>
      <PageHeader
        title={`Bonjour ${user?.full_name.split(" ")[0] ?? ""}`}
        description="Vue d'ensemble de l'activité documentaire de votre organisation."
        actions={
          <Button asChild>
            <Link to="/documents?upload=1">
              <Upload /> Déposer des documents
            </Link>
          </Button>
        }
      />

      {isLoading || !data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi icon={FileText} label="Documents" value={data.documents_total.toLocaleString("fr-FR")}
               sub={`${data.by_status.published} publiés`} to="/documents" />
          <Kpi icon={ClipboardCheck} label="À valider" value={data.pending_validation}
               sub="Validation humaine requise" to="/validation" />
          <Kpi icon={HardDrive} label="Stockage" value={formatBytes(data.storage_bytes)}
               sub={storagePct !== null ? `${storagePct.toFixed(1)} % du quota (${formatBytes(data.storage_quota_bytes)})` : undefined} />
          <Kpi icon={Users} label="Utilisateurs" value={data.users}
               sub={data.users_quota ? `sur ${data.users_quota} licences` : undefined} />
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Dépôts sur 30 jours" description="Nombre de documents déposés par jour" />
          <div className="h-64 p-4">
            {data && (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.uploads_last_30_days} margin={{ left: -20, right: 8, top: 8 }}>
                  <defs>
                    <linearGradient id="up" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(8, 10) + "/" + d.slice(5, 7)}
                         tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} minTickGap={24} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                  <Area type="monotone" dataKey="uploads" name="Dépôts" stroke="hsl(var(--primary))" strokeWidth={2} fill="url(#up)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Répartition par type" />
          <div className="p-4">
            {data && data.by_type.length > 0 ? (
              <>
                <div className="h-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={data.by_type} dataKey="count" nameKey="name" innerRadius={48} outerRadius={72} paddingAngle={2}>
                        {data.by_type.map((t) => (
                          <Cell key={t.name} fill={t.color} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <ul className="mt-2 space-y-1.5 text-sm">
                  {data.by_type.map((t) => (
                    <li key={t.name} className="flex items-center gap-2">
                      <span className="size-2.5 rounded-full" style={{ background: t.color }} />
                      <span className="flex-1 truncate">{t.name}</span>
                      <span className="tabular text-muted-foreground">{t.count}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="py-12 text-center text-sm text-muted-foreground">Aucun document pour l'instant.</p>
            )}
          </div>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Derniers documents" actions={<Link to="/documents" className="text-xs text-primary hover:underline">Tout voir</Link>} />
          <ul className="divide-y">
            {recent.data?.items.map((d) => (
              <li key={d.id}>
                <Link to={`/documents/${d.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-muted/50">
                  <FileText className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{d.title}</span>
                  <DocumentStatusBadge status={d.status} />
                  <span className="hidden w-28 text-right text-xs text-muted-foreground sm:block">{timeAgo(d.created_at)}</span>
                </Link>
              </li>
            ))}
            {recent.data?.items.length === 0 && (
              <li className="px-5 py-10 text-center text-sm text-muted-foreground">Déposez votre premier document pour démarrer.</li>
            )}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Santé des traitements" />
          <div className="space-y-4 p-5 text-sm">
            <div className="flex items-center gap-3">
              <Timer className="size-4 text-muted-foreground" />
              <span className="flex-1">Temps moyen d'OCR</span>
              <span className="tabular font-medium">{data?.ocr_avg_ms ? `${(data.ocr_avg_ms / 1000).toFixed(1)} s` : "—"}</span>
            </div>
            <div className="flex items-center gap-3">
              <AlertTriangle className="size-4 text-muted-foreground" />
              <span className="flex-1">Étapes en échec</span>
              <Link to="/processing?status=failed" className="tabular font-medium text-destructive hover:underline">
                {data?.failed_jobs ?? 0}
              </Link>
            </div>
            <div className="flex items-center gap-3">
              <FileText className="size-4 text-muted-foreground" />
              <span className="flex-1">En traitement</span>
              <span className="tabular font-medium">{data?.by_status.processing ?? 0}</span>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
