import { useState } from "react";
import { Lightbulb, Sparkles, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useInvalidateDocs, useJobs } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { DocumentDetail } from "@/types/api";
import { Button } from "@/components/ui/primitives";
import { Dialog } from "@/components/ui/overlay";

interface Suggestion {
  suggested_type_id?: string | null;
  suggested_type_name?: string | null;
  confidence?: number;
  reason?: string;
  applied?: boolean;
}

/** AI actions on a document: classification suggestion, (re)analysis and summary. */
export function AIBar({ doc }: { doc: DocumentDetail }) {
  const can = useCan();
  const invalidate = useInvalidateDocs();
  const active = doc.status === "processing" || doc.status === "uploaded";
  const { data: jobs, refetch } = useJobs(doc.id, active);
  const [busy, setBusy] = useState<string | null>(null);
  const [summary, setSummary] = useState<{ summary?: string; key_points?: string[]; missing_information?: string[] } | null>(null);
  const cls = jobs?.find((j) => j.step === "classification");
  const suggestion = cls?.status === "completed" ? (cls.result as Suggestion | null) : null;
  const showSuggestion = !doc.document_type && suggestion?.suggested_type_id && !suggestion.applied;
  const editable = can("metadata:update") && !doc.deleted_at;

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    try {
      await fn();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const analyze = () => run("analyze", async () => {
    await api(`/documents/${doc.id}/ai/analyze`, { method: "POST" });
    toast.success("Analyse IA lancée");
    invalidate();
    setTimeout(() => refetch(), 1500);
  });
  const applySuggestion = () => run("apply", async () => {
    await api(`/documents/${doc.id}`, { method: "PATCH", body: { document_type_id: suggestion!.suggested_type_id } });
    await api(`/documents/${doc.id}/ai/analyze`, { method: "POST" });
    toast.success(`Classé en « ${suggestion!.suggested_type_name} » — extraction en cours`);
    invalidate();
  });
  const summarize = () => run("summary", async () => {
    const r = await api<{ result: typeof summary; raw: string | null }>(`/documents/${doc.id}/ai/summary`, { method: "POST" });
    setSummary(r.result ?? { summary: r.raw ?? "" });
  });

  return (
    <div className="mb-3 flex flex-wrap items-center gap-3">
      {showSuggestion ? (
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3 rounded-lg border border-primary/30 bg-accent/60 px-4 py-2 text-sm">
          <Lightbulb className="size-4 text-primary" />
          <span>
            L'IA suggère <strong>{suggestion!.suggested_type_name}</strong>
            {typeof suggestion!.confidence === "number" && ` (confiance ${Math.round(suggestion!.confidence * 100)} %)`}
            {suggestion!.reason && <span className="text-muted-foreground"> — {suggestion!.reason}</span>}
          </span>
          {can("document:update") && <Button size="sm" className="ml-auto h-7" loading={busy === "apply"} onClick={applySuggestion}>Appliquer et extraire</Button>}
        </div>
      ) : (
        <div className="flex-1 text-xs text-muted-foreground">
          {doc.ai_status === "completed" && "Métadonnées pré-remplies par l'IA : vérifiez-les avant validation."}
          {doc.ai_status === "not_configured" && "IA non configurée pour votre organisation : saisie manuelle."}
        </div>
      )}
      <div className="flex items-center gap-2">
        {editable && <Button variant="outline" size="sm" loading={busy === "analyze"} disabled={active} onClick={analyze}><Wand2 /> Analyser avec l'IA</Button>}
        {can("ai_assistant:read") && <Button variant="outline" size="sm" loading={busy === "summary"} onClick={summarize}><Sparkles /> Résumé</Button>}
      </div>
      <Dialog open={!!summary} onOpenChange={(o) => !o && setSummary(null)} title="Résumé par Lina" size="lg">
        {summary && (
          <div className="space-y-4 text-sm">
            <p className="leading-relaxed">{summary.summary}</p>
            {!!summary.key_points?.length && (<div><h4 className="mb-1 font-medium">Points clés</h4><ul className="list-disc space-y-1 pl-5">{summary.key_points.map((k) => <li key={k}>{k}</li>)}</ul></div>)}
            {!!summary.missing_information?.length && (<div><h4 className="mb-1 font-medium">Informations manquantes</h4><ul className="list-disc space-y-1 pl-5 text-muted-foreground">{summary.missing_information.map((k) => <li key={k}>{k}</li>)}</ul></div>)}
            <p className="text-xs text-muted-foreground">Généré par IA à partir du texte du document — à vérifier avant usage.</p>
          </div>
        )}
      </Dialog>
    </div>
  );
}
