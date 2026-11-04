import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, HardDrive, Pause, Play, Plus, Users } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useSessionStore } from "@/stores/session";
import type { Plan, TenantDetail } from "@/types/api";
import { formatBytes, formatDate } from "@/utils/format";
import { Badge, Button, Card, CardHeader, Field, Input, PageHeader, Select } from "@/components/ui/primitives";
import { Dialog } from "@/components/ui/overlay";

export default function PlatformPage() {
  const caps = useSessionStore((s) => s.session?.platform_capabilities ?? []);
  const canAdmin = caps.includes("platform:administer");
  const qc = useQueryClient();
  const tenants = useQuery({ queryKey: ["platform-tenants"], queryFn: () => api<TenantDetail[]>("/platform/tenants") });
  const plans = useQuery({ queryKey: ["platform-plans"], queryFn: () => api<Plan[]>("/platform/plans") });
  const metrics = useQuery({ queryKey: ["platform-metrics"], queryFn: () => api<{ tenants: Record<string, number>; users: number; documents: number; storage_bytes: number }>("/platform/metrics") });
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["platform-tenant", selected], queryFn: () => api<TenantDetail>(`/platform/tenants/${selected}`), enabled: !!selected });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", slug: "", plan_code: "business", admin_email: "", admin_full_name: "", admin_password: "" });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["platform-tenants"] });
    qc.invalidateQueries({ queryKey: ["platform-metrics"] });
    qc.invalidateQueries({ queryKey: ["platform-tenant"] });
  };

  const create = async () => {
    setBusy(true);
    try {
      const t = await api<TenantDetail>("/platform/tenants", { method: "POST", body: { ...form, admin_password: form.admin_password || null } });
      toast.success(`Tenant ${t.name} provisionné`);
      setOpen(false);
      setSelected(t.id);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (id: string, status: string) => {
    try {
      await api(`/platform/tenants/${id}/status`, { method: "POST", body: { status } });
      toast.success(status === "suspended" ? "Tenant suspendu" : "Tenant réactivé");
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const m = metrics.data;
  return (
    <>
      <PageHeader title="Pilot — Administration plateforme" description="Vision globale : clients, plans, quotas et consommation."
                  actions={canAdmin && <Button onClick={() => setOpen(true)}><Plus /> Nouveau tenant</Button>} />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { icon: Building2, label: "Tenants actifs", value: m?.tenants.active ?? "—", sub: m ? `${m.tenants.suspended} suspendu(s)` : "" },
          { icon: Users, label: "Utilisateurs", value: m?.users ?? "—" },
          { icon: HardDrive, label: "Documents", value: m?.documents.toLocaleString("fr-FR") ?? "—" },
          { icon: HardDrive, label: "Stockage", value: formatBytes(m?.storage_bytes) },
        ].map((k) => (
          <Card key={k.label} className="p-5">
            <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-muted-foreground">{k.label}<k.icon className="size-4" /></div>
            <div className="tabular mt-3 text-2xl font-semibold">{k.value}</div>
            {k.sub && <div className="mt-1 text-xs text-muted-foreground">{k.sub}</div>}
          </Card>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <Card>
          <CardHeader title="Tenants" description={`${tenants.data?.length ?? 0} organisation(s)`} />
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
              <tr><th className="px-5 py-2.5 text-left font-medium">Organisation</th><th className="px-4 py-2.5 text-left font-medium">Plan</th><th className="px-4 py-2.5 text-left font-medium">Statut</th><th className="hidden px-4 py-2.5 text-left font-medium md:table-cell">Créé le</th></tr>
            </thead>
            <tbody className="divide-y">
              {tenants.data?.map((t) => (
                <tr key={t.id} className={`cursor-pointer hover:bg-muted/40 ${selected === t.id ? "bg-accent/40" : ""}`} onClick={() => setSelected(t.id)}>
                  <td className="px-5 py-3"><div className="font-medium">{t.name}</div><div className="font-mono text-xs text-muted-foreground">{t.slug}</div></td>
                  <td className="px-4 py-3">{t.plan?.name ?? "—"}</td>
                  <td className="px-4 py-3"><Badge tone={t.status === "active" ? "green" : t.status === "suspended" ? "amber" : "neutral"}>{t.status}</Badge></td>
                  <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">{formatDate(t.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card className="h-fit">
          <CardHeader title={detail.data?.name ?? "Détail du tenant"} description={detail.data ? `Plan ${detail.data.plan?.name}` : "Sélectionnez un tenant"} />
          {detail.data && (
            <div className="space-y-5 p-5 text-sm">
              {[
                { label: "Utilisateurs", used: detail.data.usage?.users ?? 0, limit: detail.data.quotas?.users, fmt: (v: number) => String(v) },
                { label: "Stockage", used: detail.data.usage?.storage_bytes ?? 0, limit: detail.data.quotas?.storage_bytes, fmt: formatBytes },
              ].map((q) => {
                const pct = q.limit ? Math.min(100, (q.used / q.limit) * 100) : 0;
                return (
                  <div key={q.label}>
                    <div className="mb-1.5 flex justify-between text-xs"><span className="font-medium">{q.label}</span><span className="tabular text-muted-foreground">{q.fmt(q.used)} / {q.limit !== undefined ? q.fmt(q.limit) : "∞"}</span></div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted"><div className={`h-full rounded-full ${pct > 90 ? "bg-destructive" : "bg-primary"}`} style={{ width: `${pct}%` }} /></div>
                  </div>
                );
              })}
              <div>
                <div className="mb-1.5 text-xs font-medium">Modules activés</div>
                <div className="flex flex-wrap gap-1">{detail.data.modules?.map((x) => <Badge key={x} tone="blue">{x}</Badge>)}</div>
              </div>
              <div className="text-xs text-muted-foreground">Documents : {detail.data.usage?.documents ?? 0} · Crédits IA mensuels : {detail.data.quotas?.ai_credits_monthly?.toLocaleString("fr-FR")}</div>
              {canAdmin && (
                detail.data.status === "active" ? (
                  <Button variant="outline" size="sm" onClick={() => setStatus(detail.data!.id, "suspended")}><Pause /> Suspendre</Button>
                ) : detail.data.status === "suspended" ? (
                  <Button size="sm" onClick={() => setStatus(detail.data!.id, "active")}><Play /> Réactiver</Button>
                ) : null
              )}
            </div>
          )}
        </Card>
      </div>

      <Dialog open={open} onOpenChange={setOpen} title="Provisionner un tenant" size="lg"
              description="Crée l'organisation, ses quotas, ses modules, ses rôles système, son administrateur et son espace documentaire initial."
              footer={<><Button variant="outline" onClick={() => setOpen(false)}>Annuler</Button><Button loading={busy} onClick={create}>Créer</Button></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nom de l'organisation"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value, slug: form.slug || e.target.value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") })} /></Field>
          <Field label="Identifiant (slug)"><Input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} className="font-mono text-xs" /></Field>
          <Field label="Plan">
            <Select value={form.plan_code} onChange={(e) => setForm({ ...form, plan_code: e.target.value })}>
              {plans.data?.map((p) => <option key={p.code} value={p.code}>{p.name} — {p.max_users} utilisateurs, {formatBytes(p.max_storage_bytes)}</option>)}
            </Select>
          </Field>
          <div />
          <Field label="Nom de l'administrateur"><Input value={form.admin_full_name} onChange={(e) => setForm({ ...form, admin_full_name: e.target.value })} /></Field>
          <Field label="E-mail de l'administrateur"><Input type="email" value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} /></Field>
          <div className="sm:col-span-2">
            <Field label="Mot de passe initial" hint="Facultatif si l'utilisateur existe déjà sur la plateforme"><Input type="password" autoComplete="new-password" value={form.admin_password} onChange={(e) => setForm({ ...form, admin_password: e.target.value })} /></Field>
          </div>
        </div>
      </Dialog>
    </>
  );
}
