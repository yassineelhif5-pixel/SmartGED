import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Ban, EyeOff, FileStack, RefreshCw, Scissors, Sparkles, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useDocument, useDocumentTypes, useInvalidateDocs } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { DocumentSummary, SplitState } from "@/types/api";
import { cn } from "@/utils/format";
import { Badge, Button, Card, Input, Select, Spinner } from "@/components/ui/primitives";
import { PageThumb } from "@/features/splitting/PageThumb";
import {
  isRealSplit, planFromProposal, segmentsOf, setMeta, toggleCut, toggleExcluded, toPayload, type SplitPlan,
} from "@/features/splitting/plan";

const PALETTE = ["#2563eb", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#dc2626"];

const REASONS: Record<string, string> = {
  first_page: "première page",
  page_numbering_reset: "numérotation qui repart à 1",
  document_header: "en-tête de document",
  new_reference: "nouvelle référence",
  after_blank_separator: "après une page blanche",
  confirmed_by_heuristic: "confirmé par l'analyse de structure",
};
const reasonLabel = (r: string) => {
  const key = r.split(" ")[0];
  const detail = r.includes("(") ? r.slice(r.indexOf("(")) : "";
  return REASONS[key] ? `${REASONS[key]} ${detail}`.trim() : r;
};

export default function SplitReviewPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const can = useCan();
  const invalidate = useInvalidateDocs();
  const { data: types = [] } = useDocumentTypes();
  const { data: doc } = useDocument(id);
  const { data: state, isLoading, refetch } = useQuery({
    queryKey: ["split", id], queryFn: () => api<SplitState>(`/documents/${id}/split`),
  });
  const [plan, setPlan] = useState<SplitPlan | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const proposal = state?.proposal?.status === "proposed" ? state.proposal : null;
  useEffect(() => {
    if (state?.page_count) setPlan(planFromProposal(state.page_count, proposal));
  }, [state?.proposal?.id, state?.page_count]);

  const segments = useMemo(() => (plan ? segmentsOf(plan, proposal) : []), [plan, proposal]);
  const colorOf = useMemo(() => {
    const m = new Map<number, string>();
    segments.forEach((s, i) => s.pages.forEach((p) => m.set(p, PALETTE[i % PALETTE.length])));
    return m;
  }, [segments]);

  if (isLoading || !state || !plan) return <div className="flex justify-center py-20"><Spinner className="size-6" /></div>;

  const applied = state.proposal?.status === "applied";
  const editable = can("document:create") && can("document:update") && !applied && state.status !== "archived";
  const realSplit = isRealSplit(segments, plan.pageCount);
  const ai = state.proposal?.details?.ai;

  const act = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    try {
      await fn();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const detect = () => act("detect", async () => {
    await api(`/documents/${id}/split/detect`, { method: "POST" });
    await refetch();
    toast.success("Détection relancée");
  });
  const dismiss = () => act("dismiss", async () => {
    await api(`/documents/${id}/split/dismiss`, { method: "POST" });
    invalidate();
    toast.success("Conservé comme un seul document — le traitement reprend");
    navigate(`/documents/${id}`);
  });
  const apply = () => act("apply", async () => {
    const r = await api<{ children: DocumentSummary[] }>(`/documents/${id}/split/apply`, {
      method: "POST", body: { segments: toPayload(segments), proposal_id: proposal?.id ?? null },
    });
    invalidate();
    toast.success(`${r.children.length} documents créés — classification et extraction en cours`);
    navigate(`/documents/${id}`);
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)} aria-label="Retour"><ArrowLeft /></Button>
        <div className="min-w-0 flex-1">
          <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight"><Scissors className="size-5 text-primary" /> Découpage du lot</h1>
          <p className="mt-0.5 truncate text-sm text-muted-foreground">
            <Link to={`/documents/${id}`} className="hover:underline">{doc?.title ?? "Document"}</Link> · {plan.pageCount} pages
          </p>
        </div>
        {editable && (
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" loading={busy === "detect"} onClick={detect}><RefreshCw /> Relancer la détection</Button>
            {proposal && <Button variant="outline" size="sm" loading={busy === "dismiss"} onClick={dismiss}><Ban /> Un seul document</Button>}
            <Button size="sm" loading={busy === "apply"} disabled={!realSplit} onClick={apply}>
              <FileStack /> Créer {segments.length} document{segments.length > 1 ? "s" : ""}
            </Button>
          </div>
        )}
      </div>

      <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-sm">
        {state.proposal ? (
          <>
            <span className="flex items-center gap-2">
              {state.proposal.method === "ai" ? <Sparkles className="size-4 text-primary" /> : <Scissors className="size-4 text-muted-foreground" />}
              Détection {state.proposal.method === "ai" ? "par l'IA" : state.proposal.method === "manual" ? "manuelle" : "par analyse de structure"}
            </span>
            {state.proposal.confidence != null && (
              <span>Confiance des coupures : <strong className="tabular">{Math.round(state.proposal.confidence * 100)} %</strong></span>
            )}
            <span className="text-muted-foreground">
              {ai?.status === "not_configured" && "IA non configurée : détection par structure (numérotation, en-têtes, pages blanches)."}
              {ai?.status === "disabled" && "Détection IA désactivée pour votre organisation."}
              {ai?.error && <span title={ai.error}>L'IA n'a pas fourni de découpage exploitable : proposition issue de l'analyse de structure.</span>}
            </span>
            {applied && <Badge tone="green">Découpage appliqué</Badge>}
            {state.proposal.status === "dismissed" && <Badge tone="neutral">Conservé comme document unique</Badge>}
          </>
        ) : (
          <span className="text-muted-foreground">Aucune proposition : placez les coupures vous-même entre les pages.</span>
        )}
      </Card>

      {applied && (
        <Card className="px-4 py-3 text-sm">
          Ce lot a été découpé en {state.proposal!.child_document_ids.length} documents.{" "}
          <Link className="font-medium text-primary hover:underline" to={`/documents/${id}`}>Voir les documents créés</Link>
        </Card>
      )}

      {editable && (
        <p className="text-xs text-muted-foreground">
          Cliquez sur <Scissors className="inline size-3" /> entre deux pages pour couper ou recoller. Une page exclue (page blanche, intercalaire) n'est reprise dans aucun document et termine le document en cours.
        </p>
      )}

      <div className="space-y-4">
        {segments.map((seg, index) => {
          const color = PALETTE[index % PALETTE.length];
          return (
            <Card key={seg.start} className="overflow-hidden">
              <div className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5" style={{ borderLeft: `4px solid ${color}` }}>
                <span className="tabular text-sm font-semibold">Document {index + 1}</span>
                <Badge tone="outline">p. {seg.start === seg.end ? seg.start : `${seg.start}–${seg.end}`}</Badge>
                {seg.source?.confidence != null && index > 0 && (
                  <Badge tone={seg.source.confidence >= 0.8 ? "green" : seg.source.confidence >= 0.6 ? "amber" : "red"}>
                    {Math.round(seg.source.confidence * 100)} %
                  </Badge>
                )}
                {!!seg.source?.reasons?.length && (
                  <span className="truncate text-xs text-muted-foreground">{seg.source.reasons.filter((r) => !r.startsWith("continuation")).map(reasonLabel).join(" · ")}</span>
                )}
                <div className="ml-auto flex min-w-[18rem] flex-1 flex-wrap gap-2 sm:flex-none">
                  <Input
                    className="h-8 w-56" placeholder={`${doc?.title ?? "Document"} — partie ${index + 1}`} value={seg.title}
                    disabled={!editable} aria-label={`Titre du document ${index + 1}`}
                    onChange={(e) => setPlan((p) => p && setMeta(p, seg.start, { title: e.target.value }))}
                  />
                  <Select
                    className="h-8 w-44" value={seg.typeId} disabled={!editable} aria-label={`Type du document ${index + 1}`}
                    onChange={(e) => setPlan((p) => p && setMeta(p, seg.start, { typeId: e.target.value }))}
                  >
                    <option value="">Type : classification auto</option>
                    {types.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </Select>
                </div>
              </div>
              <div className="flex flex-wrap items-start gap-y-4 p-4">
                {seg.pages.map((p, i) => (
                  <Fragment key={p}>
                    {i > 0 && editable && (
                      <CutButton label={`Couper avant la page ${p}`} onClick={() => setPlan((pl) => pl && toggleCut(pl, p))} />
                    )}
                    {i > 0 && !editable && <span className="w-3" />}
                    <PageCard docId={id} page={p} excerpt={state.pages[p - 1]?.excerpt ?? ""} color={colorOf.get(p)}
                              editable={editable} onExclude={() => setPlan((pl) => pl && toggleExcluded(pl, p))} />
                  </Fragment>
                ))}
                {editable && index < segments.length - 1 && segments[index + 1].start === seg.end + 1 && (
                  <button
                    onClick={() => setPlan((pl) => pl && toggleCut(pl, segments[index + 1].start))}
                    className="ml-3 flex h-32 items-center gap-1 self-center rounded-md border border-dashed px-3 text-xs text-muted-foreground hover:border-primary hover:text-primary"
                  >
                    <Undo2 className="size-3.5" /> Recoller au suivant
                  </button>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      {plan.excluded.size > 0 && (
        <div>
          <h2 className="mb-2 flex items-center gap-2 text-sm font-medium"><EyeOff className="size-4" /> Pages exclues</h2>
          <div className="flex flex-wrap gap-3">
            {[...plan.excluded].sort((a, b) => a - b).map((p) => (
              <div key={p} className="w-28 space-y-1">
                <PageThumb docId={id} page={p} excerpt={state.pages[p - 1]?.excerpt ?? ""} dimmed />
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Page {p}</span>
                  {editable && <button className="text-primary hover:underline" onClick={() => setPlan((pl) => pl && toggleExcluded(pl, p))}>Réintégrer</button>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CutButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick} aria-label={label} title={label}
      className="group mx-1 flex h-40 w-5 items-center justify-center self-center"
    >
      <span className="flex size-6 items-center justify-center rounded-full border bg-card text-muted-foreground opacity-50 shadow-sm transition group-hover:border-primary group-hover:text-primary group-hover:opacity-100">
        <Scissors className="size-3" />
      </span>
    </button>
  );
}

function PageCard({ docId, page, excerpt, color, editable, onExclude }: {
  docId: string; page: number; excerpt: string; color?: string; editable: boolean; onExclude: () => void;
}) {
  return (
    <div className="w-28 space-y-1 sm:w-32">
      <div className={cn("rounded-md p-0.5")} style={{ boxShadow: color ? `0 0 0 2px ${color}33` : undefined }}>
        <PageThumb docId={docId} page={page} excerpt={excerpt} />
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="tabular">Page {page}</span>
        {editable && (
          <button className="hover:text-destructive" onClick={onExclude} title="Exclure cette page (page blanche, intercalaire)">
            Exclure
          </button>
        )}
      </div>
    </div>
  );
}
