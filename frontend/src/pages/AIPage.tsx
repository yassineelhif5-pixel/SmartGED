import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CheckCircle2, CircleSlash, FlaskConical, KeyRound, Pencil, Plug, Plus, RotateCcw, Rocket, Star, Trash2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useDocuments } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { AIProviderT, AIUsage, Prompt, PromptTestResult, PromptVersion, ProviderKind } from "@/types/api";
import { cn, formatDateTime, timeAgo } from "@/utils/format";
import { Badge, Button, Card, CardHeader, EmptyState, Field, Input, PageHeader, Select, Switch, Textarea } from "@/components/ui/primitives";
import { ConfirmDialog, Dialog } from "@/components/ui/overlay";

const KINDS: { value: ProviderKind; label: string; key: boolean; url: "none" | "optional" | "required"; hint: string }[] = [
  { value: "anthropic", label: "Anthropic (Claude)", key: true, url: "none", hint: "ex. claude-sonnet-5-5" },
  { value: "openai", label: "OpenAI", key: true, url: "none", hint: "nom du modèle OpenAI" },
  { value: "azure_openai", label: "Azure OpenAI", key: true, url: "required", hint: "nom du déploiement Azure" },
  { value: "gemini", label: "Google Gemini", key: true, url: "none", hint: "nom du modèle Gemini" },
  { value: "openai_compatible", label: "Compatible OpenAI (Ollama, vLLM, Mistral…)", key: false, url: "required", hint: "ex. llama3.1" },
];
const kindLabel = (k: string) => KINDS.find((x) => x.value === k)?.label ?? k;

export default function AIPage() {
  const [tab, setTab] = useState<"providers" | "prompts" | "usage">("providers");
  return (
    <>
      <PageHeader title="Intelligence IA"
                  description="Fournisseurs d'IA de votre organisation, consignes (prompts) versionnées et consommation. Le pipeline classe les documents et extrait leurs métadonnées avec ces réglages." />
      <div className="mb-5 flex gap-1 border-b" role="tablist">
        {([["providers", "Fournisseurs"], ["prompts", "Prompt Studio"], ["usage", "Consommation"]] as const).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                  className={cn("border-b-2 px-4 py-2 text-sm font-medium", tab === k ? "border-primary" : "border-transparent text-muted-foreground")}>{l}</button>
        ))}
      </div>
      {tab === "providers" && <Providers />}
      {tab === "prompts" && <PromptStudio />}
      {tab === "usage" && <Usage />}
    </>
  );
}

// ---------------------------------------------------------------- providers
type ProviderForm = {
  id?: string; name: string; kind: ProviderKind; base_url: string; api_version: string; api_key: string; key_set: boolean;
  default_model: string; temperature: string; max_tokens: number; timeout_seconds: number; is_active: boolean; is_default: boolean; fallback_provider_id: string;
};

function Providers() {
  const can = useCan();
  const qc = useQueryClient();
  const admin = can("tenant_settings:administer");
  const { data: providers = [], isLoading } = useQuery({ queryKey: ["ai-providers"], queryFn: () => api<AIProviderT[]>("/ai/providers") });
  const [form, setForm] = useState<ProviderForm | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<AIProviderT | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["ai-providers"] });
  const spec = KINDS.find((k) => k.value === form?.kind);

  const open = (p?: AIProviderT) => setForm(p
    ? { id: p.id, name: p.name, kind: p.kind, base_url: p.base_url ?? "", api_version: p.api_version ?? "", api_key: "", key_set: p.api_key_set,
        default_model: p.default_model, temperature: p.temperature === null ? "" : String(p.temperature), max_tokens: p.max_tokens,
        timeout_seconds: p.timeout_seconds, is_active: p.is_active, is_default: p.is_default, fallback_provider_id: p.fallback_provider_id ?? "" }
    : { name: "", kind: "anthropic", base_url: "", api_version: "", api_key: "", key_set: false, default_model: "", temperature: "", max_tokens: 2048,
        timeout_seconds: 60, is_active: true, is_default: providers.length === 0, fallback_provider_id: "" });

  const save = async () => {
    if (!form) return;
    setBusy("save");
    try {
      const body = {
        name: form.name, kind: form.kind, base_url: form.base_url || null, api_version: form.api_version || null,
        api_key: form.api_key || null, default_model: form.default_model, temperature: form.temperature === "" ? null : Number(form.temperature),
        max_tokens: form.max_tokens, timeout_seconds: form.timeout_seconds, is_active: form.is_active, is_default: form.is_default,
        fallback_provider_id: form.fallback_provider_id || null,
      };
      await api(form.id ? `/ai/providers/${form.id}` : "/ai/providers", { method: form.id ? "PUT" : "POST", body });
      toast.success("Fournisseur enregistré");
      setForm(null);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const test = async (p: AIProviderT) => {
    setBusy(p.id);
    try {
      const r = await api<AIProviderT>(`/ai/providers/${p.id}/test`, { method: "POST" });
      if (r.last_test_ok) toast.success(r.last_test_message ?? "Connexion réussie");
      else toast.error(r.last_test_message ?? "Échec");
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Les clés API sont chiffrées en base et ne sont jamais renvoyées au navigateur.</p>
        {admin && <Button onClick={() => open()}><Plus /> Ajouter un fournisseur</Button>}
      </div>
      {!isLoading && providers.length === 0 ? (
        <Card><EmptyState icon={Plug} title="Aucun fournisseur IA configuré"
                          description="Sans fournisseur, la classification et l'extraction restent « non configurées » : rien n'est simulé. Ajoutez une clé API pour activer l'intelligence documentaire."
                          action={admin ? <Button onClick={() => open()}><Plus /> Ajouter un fournisseur</Button> : undefined} /></Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {providers.map((p) => (
            <Card key={p.id} className="p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate font-semibold">{p.name}</h3>
                    {p.is_default && <Badge tone="blue"><Star className="size-3" /> par défaut</Badge>}
                    {!p.is_active && <Badge tone="neutral">inactif</Badge>}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{kindLabel(p.kind)} · <span className="font-mono">{p.default_model}</span></p>
                </div>
                {admin && (
                  <div className="flex gap-1">
                    <Button size="icon" variant="ghost" aria-label="Modifier" onClick={() => open(p)}><Pencil /></Button>
                    <Button size="icon" variant="ghost" aria-label="Supprimer" onClick={() => setToDelete(p)}><Trash2 className="text-destructive" /></Button>
                  </div>
                )}
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
                <dt className="text-muted-foreground">Clé API</dt><dd className="font-mono">{p.api_key_set ? p.api_key_hint : "—"}</dd>
                {p.base_url && <><dt className="text-muted-foreground">Endpoint</dt><dd className="truncate">{p.base_url}</dd></>}
                <dt className="text-muted-foreground">Max tokens / timeout</dt><dd>{p.max_tokens} · {p.timeout_seconds} s</dd>
                {p.fallback_provider_id && <><dt className="text-muted-foreground">Secours</dt><dd>{providers.find((x) => x.id === p.fallback_provider_id)?.name}</dd></>}
              </dl>
              <div className="mt-4 flex items-center gap-3 border-t pt-3 text-xs">
                {p.last_test_ok === null ? <span className="text-muted-foreground">Jamais testé</span>
                  : p.last_test_ok ? <span className="flex items-center gap-1 text-success"><CheckCircle2 className="size-3.5" /> {p.last_test_message}</span>
                  : <span className="flex min-w-0 items-center gap-1 text-destructive" title={p.last_test_message ?? ""}><XCircle className="size-3.5 shrink-0" /><span className="truncate">{p.last_test_message}</span></span>}
                {p.last_test_at && <span className="text-muted-foreground">{timeAgo(p.last_test_at)}</span>}
                {admin && <Button size="sm" variant="outline" className="ml-auto h-7" loading={busy === p.id} onClick={() => test(p)}><Plug /> Tester</Button>}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!form} onOpenChange={(o) => !o && setForm(null)} title={form?.id ? "Modifier le fournisseur" : "Nouveau fournisseur IA"} size="lg"
              footer={<><Button variant="outline" onClick={() => setForm(null)}>Annuler</Button><Button loading={busy === "save"} disabled={!form?.name || !form?.default_model} onClick={save}>Enregistrer</Button></>}>
        {form && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nom"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="ex. Claude production" /></Field>
            <Field label="Fournisseur">
              <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as ProviderKind })}>
                {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
              </Select>
            </Field>
            <Field label="Modèle" hint={spec?.hint}><Input className="font-mono text-xs" value={form.default_model} onChange={(e) => setForm({ ...form, default_model: e.target.value })} /></Field>
            <Field label={`Clé API${spec?.key ? "" : " (facultative)"}`} hint={form.key_set ? "Laisser vide pour conserver la clé actuelle" : undefined}>
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input type="password" autoComplete="off" className="pl-9" value={form.api_key} placeholder={form.key_set ? "•••••••• (enregistrée)" : ""}
                       onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
              </div>
            </Field>
            {spec?.url !== "none" && (
              <Field label="URL de l'API / endpoint" hint={form.kind === "azure_openai" ? "https://<ressource>.openai.azure.com" : "ex. http://ollama:11434/v1"}>
                <Input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
              </Field>
            )}
            {form.kind === "azure_openai" && <Field label="Version d'API Azure"><Input value={form.api_version} placeholder="2024-10-21" onChange={(e) => setForm({ ...form, api_version: e.target.value })} /></Field>}
            <Field label="Température" hint="Vide = valeur du modèle. 0 recommandé pour l'extraction"><Input inputMode="decimal" value={form.temperature} onChange={(e) => setForm({ ...form, temperature: e.target.value })} /></Field>
            <Field label="Tokens de sortie max"><Input type="number" value={form.max_tokens} onChange={(e) => setForm({ ...form, max_tokens: Number(e.target.value) })} /></Field>
            <Field label="Timeout (s)"><Input type="number" value={form.timeout_seconds} onChange={(e) => setForm({ ...form, timeout_seconds: Number(e.target.value) })} /></Field>
            <Field label="Fournisseur de secours" hint="Utilisé si celui-ci échoue après 3 tentatives">
              <Select value={form.fallback_provider_id} onChange={(e) => setForm({ ...form, fallback_provider_id: e.target.value })}>
                <option value="">Aucun</option>
                {providers.filter((p) => p.id !== form.id).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
            </Field>
            <div className="flex flex-wrap gap-6 text-sm sm:col-span-2">
              <label className="flex items-center gap-2"><Switch checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} /> Actif</label>
              <label className="flex items-center gap-2"><Switch checked={form.is_default} onChange={(v) => setForm({ ...form, is_default: v })} /> Fournisseur par défaut du pipeline</label>
            </div>
          </div>
        )}
      </Dialog>
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} destructive title="Supprimer le fournisseur ?" confirmLabel="Supprimer"
                     description="La clé chiffrée sera effacée. L'historique de consommation est conservé."
                     onConfirm={async () => { try { await api(`/ai/providers/${toDelete!.id}`, { method: "DELETE" }); toast.success("Fournisseur supprimé"); setToDelete(null); refresh(); } catch (e) { toast.error((e as Error).message); } }} />
    </>
  );
}

// ------------------------------------------------------------ prompt studio
const STATUS_TONE = { draft: "amber", published: "green", archived: "neutral" } as const;
const STATUS_LABEL = { draft: "brouillon", published: "publiée", archived: "archivée" } as const;

function PromptStudio() {
  const can = useCan();
  const qc = useQueryClient();
  const { data: prompts = [] } = useQuery({ queryKey: ["ai-prompts"], queryFn: () => api<Prompt[]>("/ai/prompts") });
  const codes = useMemo(() => [...new Set(prompts.map((p) => p.code))], [prompts]);
  const [code, setCode] = useState<string>("");
  const [versionId, setVersionId] = useState<string>("");
  const [draft, setDraft] = useState<{ system_prompt: string; user_template: string; model: string; notes: string } | null>(null);
  const [docId, setDocId] = useState("");
  const [result, setResult] = useState<PromptTestResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const docs = useDocuments({ page_size: 50, sort: "created_at", order: "desc" });

  useEffect(() => { if (!code && codes.length) setCode(codes[0]); }, [codes, code]);
  const slot = prompts.filter((p) => p.code === code);
  const effective = slot.find((p) => p.effective) ?? slot[0];
  const allVersions: (PromptVersion & { scope: string; promptId: string })[] = slot.flatMap((p) => p.versions.map((v) => ({ ...v, scope: p.scope, promptId: p.id })));
  const selected = allVersions.find((v) => v.id === versionId) ?? allVersions.find((v) => v.status === "published" && effective && effective.versions.some((x) => x.id === v.id)) ?? allVersions[0];
  const tenantPrompt = slot.find((p) => p.scope === "tenant");
  useEffect(() => { setResult(null); setDraft(null); }, [code, versionId]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["ai-prompts"] });

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    try { await fn(); } catch (e) { toast.error((e as Error).message); } finally { setBusy(null); }
  };

  const saveDraft = () => run("save", async () => {
    const r = await api<Prompt>(`/ai/prompts/${code}/versions`, { method: "POST", body: { ...draft, model: draft!.model || null, notes: draft!.notes || null } });
    toast.success(`Version ${r.versions[0].version} créée (brouillon)`);
    setDraft(null);
    setVersionId(r.versions[0].id);
    refresh();
  });
  const test = () => run("test", async () => {
    const r = await api<PromptTestResult>("/ai/prompts/test", { method: "POST", body: { version_id: selected!.id, document_id: docId } });
    setResult(r);
    if (r.ok) toast.success("Test réussi"); else toast.error(r.error ?? "Échec du test");
  });
  const publish = () => run("publish", async () => {
    await api(`/ai/prompts/versions/${selected!.id}/publish`, { method: "POST" });
    toast.success(`Version ${selected!.version} publiée : le pipeline l'utilise désormais`);
    refresh();
  });
  const reset = () => run("reset", async () => {
    await api(`/ai/prompts/${tenantPrompt!.id}/reset`, { method: "POST" });
    toast.success("Retour à la consigne plateforme");
    refresh();
  });

  return (
    <div className="grid gap-6 xl:grid-cols-[260px_1fr]">
      <Card className="h-fit p-2">
        {codes.map((c) => {
          const ps = prompts.filter((p) => p.code === c);
          const eff = ps.find((p) => p.effective);
          return (
            <button key={c} onClick={() => { setCode(c); setVersionId(""); }}
                    className={cn("w-full rounded-md px-3 py-2.5 text-left text-sm", c === code ? "bg-accent" : "hover:bg-muted")}>
              <span className="block font-medium">{ps[0].name}</span>
              <span className="text-xs text-muted-foreground">{eff?.scope === "tenant" ? `Personnalisé · v${eff.published_version}` : "Consigne plateforme"}</span>
            </button>
          );
        })}
      </Card>

      {selected && (
        <div className="space-y-4">
          <Card className="p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">Versions :</span>
              {allVersions.map((v) => (
                <button key={v.id} onClick={() => setVersionId(v.id)}
                        className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs", selected.id === v.id ? "border-primary bg-accent" : "hover:bg-muted")}>
                  {v.scope === "platform" ? "Plateforme" : "Org."} v{v.version}
                  <Badge tone={STATUS_TONE[v.status]}>{STATUS_LABEL[v.status]}</Badge>
                </button>
              ))}
              <div className="ml-auto flex gap-2">
                {tenantPrompt?.effective && can("prompt:administer") && <Button size="sm" variant="ghost" loading={busy === "reset"} onClick={reset}><RotateCcw /> Revenir à la plateforme</Button>}
                {can("prompt:create") && !draft && (
                  <Button size="sm" variant="outline" onClick={() => setDraft({ system_prompt: selected.system_prompt, user_template: selected.user_template, model: selected.model ?? "", notes: "" })}>
                    <Pencil /> Nouvelle version à partir de celle-ci
                  </Button>
                )}
              </div>
            </div>
            {effective && <p className="mt-2 text-xs text-muted-foreground">{effective.description}</p>}
          </Card>

          <Card>
            <CardHeader title={draft ? "Nouvelle version (brouillon)" : `Version ${selected.version} — ${STATUS_LABEL[selected.status]}`}
                        description={`Variables : ${(draft ? [] : selected.variables).map((v) => `{{${v}}}`).join(" ") || "{{document_content}}, {{document_type}}, {{metadata_schema}}, {{document_types}}, {{language}}, {{business_rules}}…"}`} />
            <div className="space-y-4 p-5">
              <Field label="Consigne système">
                <Textarea rows={5} className="font-mono text-xs" readOnly={!draft} value={draft ? draft.system_prompt : selected.system_prompt}
                          onChange={(e) => draft && setDraft({ ...draft, system_prompt: e.target.value })} />
              </Field>
              <Field label="Modèle de message" hint="Le contenu du document doit rester entre <document> et </document> (protection contre l'injection de consignes).">
                <Textarea rows={12} className="font-mono text-xs" readOnly={!draft} value={draft ? draft.user_template : selected.user_template}
                          onChange={(e) => draft && setDraft({ ...draft, user_template: e.target.value })} />
              </Field>
              {draft && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Modèle IA spécifique (facultatif)"><Input className="font-mono text-xs" value={draft.model} onChange={(e) => setDraft({ ...draft, model: e.target.value })} /></Field>
                  <Field label="Note de version"><Input value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} /></Field>
                  <div className="flex gap-2 sm:col-span-2">
                    <Button loading={busy === "save"} onClick={saveDraft}>Enregistrer le brouillon</Button>
                    <Button variant="ghost" onClick={() => setDraft(null)}>Annuler</Button>
                  </div>
                </div>
              )}
            </div>
          </Card>

          {!draft && (
            <Card>
              <CardHeader title="Tester avant publication" description="Exécute cette version sur un vrai document avec votre fournisseur par défaut (consomme des crédits)." />
              <div className="space-y-4 p-5">
                <div className="flex flex-wrap gap-2">
                  <Select className="max-w-md" value={docId} onChange={(e) => setDocId(e.target.value)}>
                    <option value="">Choisir un document…</option>
                    {docs.data?.items.map((d) => <option key={d.id} value={d.id}>{d.title}{d.document_type ? ` (${d.document_type.name})` : ""}</option>)}
                  </Select>
                  {can("prompt:update") && <Button variant="outline" disabled={!docId} loading={busy === "test"} onClick={test}><FlaskConical /> Lancer le test</Button>}
                  {selected.scope === "tenant" && selected.status !== "published" && can("prompt:administer") && (
                    <Button loading={busy === "publish"} onClick={publish}><Rocket /> Publier la v{selected.version}</Button>
                  )}
                </div>
                {result && (
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                      <Badge tone={result.ok ? "green" : "red"}>{result.ok ? "JSON valide" : "Échec"}</Badge>
                      {result.model && <span>{result.provider} · <span className="font-mono">{result.model}</span></span>}
                      {result.input_tokens !== null && <span>{result.input_tokens} → {result.output_tokens} tokens</span>}
                      {result.latency_ms !== null && <span>{(result.latency_ms / 1000).toFixed(1)} s</span>}
                      {result.credits !== null && <span>{result.credits} crédit(s)</span>}
                      {result.estimated_cost !== null && <span>≈ {Number(result.estimated_cost).toFixed(4)} $</span>}
                    </div>
                    <pre className="max-h-80 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-xs">
                      {result.error ?? JSON.stringify(result.parsed ?? result.output_text, null, 2)}
                    </pre>
                  </div>
                )}
                {selected.scope === "platform" && <p className="text-xs text-muted-foreground">Les versions plateforme ne se publient pas : créez une version de votre organisation pour personnaliser cette consigne.</p>}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- usage
const FEATURE_LABELS: Record<string, string> = {
  classification: "Classification", metadata_extraction: "Extraction des métadonnées", document_summary: "Résumé",
  prompt_test: "Tests de prompts", connection_test: "Tests de connexion",
};

function Usage() {
  const { data } = useQuery({ queryKey: ["ai-usage"], queryFn: () => api<AIUsage>("/ai/usage", { query: { days: 30 } }), refetchInterval: 30000 });
  if (!data) return null;
  const pct = data.credits_limit_month ? Math.min(100, (data.credits_used_month / data.credits_limit_month) * 100) : 0;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-5">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Crédits ce mois</div>
          <div className="tabular mt-3 text-2xl font-semibold">{data.credits_used_month.toLocaleString("fr-FR")}<span className="text-sm font-normal text-muted-foreground"> / {data.credits_limit_month?.toLocaleString("fr-FR") ?? "∞"}</span></div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"><div className={cn("h-full", pct > 90 ? "bg-destructive" : "bg-primary")} style={{ width: `${pct}%` }} /></div>
        </Card>
        <Card className="p-5"><div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Appels (30 j)</div><div className="tabular mt-3 text-2xl font-semibold">{data.totals.calls}</div><div className="mt-1 text-xs text-muted-foreground">{data.totals.errors} en erreur</div></Card>
        <Card className="p-5"><div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Tokens (30 j)</div><div className="tabular mt-3 text-2xl font-semibold">{(data.totals.input_tokens + data.totals.output_tokens).toLocaleString("fr-FR")}</div><div className="mt-1 text-xs text-muted-foreground">{data.totals.avg_latency_ms ? `latence moy. ${(data.totals.avg_latency_ms / 1000).toFixed(1)} s` : ""}</div></Card>
        <Card className="p-5"><div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Coût estimé (30 j)</div><div className="tabular mt-3 text-2xl font-semibold">{data.totals.cost !== null ? `${data.totals.cost.toFixed(2)} $` : "—"}</div><div className="mt-1 text-xs text-muted-foreground">selon les tarifs configurés</div></Card>
      </div>
      <Card>
        <CardHeader title="Crédits consommés par jour" />
        <div className="h-56 p-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.per_day} margin={{ left: -20, right: 8, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="date" tickFormatter={(d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}`} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="credits" name="Crédits" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        {([["Par fonctionnalité", data.by_feature, (k: string) => FEATURE_LABELS[k] ?? k], ["Par modèle", data.by_model, (k: string) => k]] as const).map(([title, rows, label]) => (
          <Card key={title}>
            <CardHeader title={title} />
            {rows.length === 0 ? <EmptyState icon={CircleSlash} title="Aucune consommation sur la période" /> : (
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-xs text-muted-foreground"><tr><th className="px-4 py-2 text-left font-medium"> </th><th className="px-4 py-2 text-right font-medium">Appels</th><th className="px-4 py-2 text-right font-medium">Tokens</th><th className="px-4 py-2 text-right font-medium">Crédits</th></tr></thead>
                <tbody className="divide-y">{rows.map((r) => (
                  <tr key={r.key}><td className="px-4 py-2">{label(r.key)}</td><td className="tabular px-4 py-2 text-right">{r.calls}</td><td className="tabular px-4 py-2 text-right">{r.tokens.toLocaleString("fr-FR")}</td><td className="tabular px-4 py-2 text-right font-medium">{r.credits}</td></tr>
                ))}</tbody>
              </table>
            )}
          </Card>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">1 crédit = 0,001 $ de coût estimé ; sans tarif configuré pour un modèle, 1 crédit par tranche de 1 000 tokens. Mis à jour {formatDateTime(new Date().toISOString())}.</p>
    </div>
  );
}
