import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Download, FileUp, Link2 } from "lucide-react";
import { toast } from "sonner";
import { api, downloadFile } from "@/api/client";
import { useInvalidateDocs, useJobs, usePages, useRelations, useVersions } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { DocumentDetail } from "@/types/api";
import { formatBytes, formatDateTime } from "@/utils/format";
import { Button, Field, Input, Spinner } from "@/components/ui/primitives";
import { Dialog } from "@/components/ui/overlay";
import { STEP_LABELS, StepBadge } from "@/components/StatusBadge";

export function TextPanel({ doc }: { doc: DocumentDetail }) {
  const { data, isLoading } = usePages(doc.id, doc.current_version);
  if (isLoading) return <div className="p-6"><Spinner /></div>;
  if (!data?.length)
    return (
      <p className="p-6 text-sm text-muted-foreground">
        {doc.ocr_status === "not_configured" ? "Aucun moteur OCR n'est configuré pour ce format." : "Aucun texte extrait pour le moment."}
      </p>
    );
  return (
    <div className="h-full space-y-4 overflow-y-auto p-5">
      {data.map((p) => (
        <section key={p.page_number}>
          <div className="mb-1.5 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Page {p.page_number}</span>
            <span>· {p.method === "tesseract" ? "OCR Tesseract" : p.method === "text_layer" ? "Couche texte" : p.method}</span>
            {p.confidence !== null && p.method === "tesseract" && <span>· confiance {Math.round(p.confidence * 100)} %</span>}
          </div>
          <pre className="whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-mono text-xs leading-relaxed">
            {p.text || "(page sans texte)"}
          </pre>
        </section>
      ))}
    </div>
  );
}

export function ProcessingPanel({ doc }: { doc: DocumentDetail }) {
  const active = doc.status === "processing" || doc.status === "uploaded";
  const { data } = useJobs(doc.id, active);
  const can = useCan();
  const invalidate = useInvalidateDocs();
  const [busy, setBusy] = useState(false);
  const reprocess = async () => {
    setBusy(true);
    try {
      await api(`/documents/${doc.id}/reprocess`, { method: "POST" });
      toast.success("Traitement relancé");
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="h-full overflow-y-auto p-5">
      <ol className="relative space-y-4 border-l pl-5">
        {data?.map((j) => (
          <li key={j.id} className="relative">
            <span className="absolute -left-[25px] top-1 size-2.5 rounded-full border-2 border-card bg-primary" />
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{STEP_LABELS[j.step] ?? j.step}</span>
              <StepBadge status={j.status} />
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              {j.duration_ms !== null && `${j.duration_ms} ms`}
              {j.attempts > 1 && ` · ${j.attempts} tentatives`}
              {j.result && "reason" in j.result && ` · ${String(j.result.reason)}`}
              {j.result && "pages" in j.result && ` · ${String(j.result.pages)} page(s), ${String(j.result.chars)} caractères`}
            </div>
            {j.error && <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded bg-destructive/5 p-2 text-[11px] text-destructive">{j.error.split("\n")[0]}</pre>}
          </li>
        ))}
      </ol>
      {can("processing:administer") && !doc.deleted_at && (
        <Button variant="outline" size="sm" className="mt-6" loading={busy} onClick={reprocess}>Relancer le traitement</Button>
      )}
    </div>
  );
}

export function VersionsPanel({ doc }: { doc: DocumentDetail }) {
  const { data, refetch } = useVersions(doc.id);
  const can = useCan();
  const invalidate = useInvalidateDocs();
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("file", file);
    if (comment) fd.append("comment", comment);
    try {
      await api(`/documents/${doc.id}/versions`, { method: "POST", body: fd });
      toast.success("Nouvelle version déposée");
      setOpen(false);
      setComment("");
      invalidate();
      refetch();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-5">
      {can("document:update") && !doc.deleted_at && (
        <Button size="sm" variant="outline" className="mb-4" onClick={() => setOpen(true)}>
          <FileUp /> Nouvelle version
        </Button>
      )}
      <ul className="space-y-2">
        {data?.map((v) => (
          <li key={v.id} className="flex items-center gap-3 rounded-md border p-3">
            <span className="flex size-8 items-center justify-center rounded-md bg-accent text-xs font-semibold text-accent-foreground">v{v.version_number}</span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{v.comment || v.file_name}</div>
              <div className="text-xs text-muted-foreground">{formatDateTime(v.created_at)} · {formatBytes(v.file_size)}</div>
              <div className="truncate font-mono text-[10px] text-muted-foreground" title="SHA-256">{v.sha256}</div>
            </div>
            {can("document:download") && (
              <Button variant="ghost" size="icon" aria-label={`Télécharger v${v.version_number}`}
                      onClick={() => downloadFile(`/documents/${doc.id}/download`, v.file_name, { version: v.version_number }).catch((e) => toast.error(e.message))}>
                <Download />
              </Button>
            )}
          </li>
        ))}
      </ul>
      <Dialog open={open} onOpenChange={setOpen} title="Déposer une nouvelle version" size="sm"
              footer={<><Button variant="outline" onClick={() => setOpen(false)}>Annuler</Button><Button loading={busy} onClick={upload}>Déposer</Button></>}>
        <div className="space-y-4">
          <Field label="Fichier"><Input type="file" ref={fileRef} /></Field>
          <Field label="Commentaire"><Input value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} /></Field>
        </div>
      </Dialog>
    </div>
  );
}

export function RelationsPanel({ doc }: { doc: DocumentDetail }) {
  const { data } = useRelations(doc.id);
  if (!data?.length) return <p className="p-6 text-sm text-muted-foreground">Aucune relation documentaire.</p>;
  return (
    <ul className="space-y-2 p-5">
      {data.map((r) => (
        <li key={r.id}>
          <Link to={`/documents/${r.document.id}`} className="flex items-center gap-3 rounded-md border p-3 hover:bg-muted/50">
            <Link2 className="size-4 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{r.document.title}</div>
              <div className="text-xs text-muted-foreground">{relationLabel(r.relation_type, r.direction)}</div>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function InfoPanel({ doc }: { doc: DocumentDetail }) {
  const rows: [string, React.ReactNode][] = [
    ["Fichier d'origine", doc.original_file_name],
    ["Format", `${doc.mime_type}`],
    ["Taille", formatBytes(doc.file_size)],
    ["Pages", doc.page_count ?? "—"],
    ["Langue détectée", doc.language?.toUpperCase() ?? "—"],
    ["Version courante", `v${doc.current_version}`],
    ["Propriétaire", doc.owner_name ?? "—"],
    ["Déposé le", formatDateTime(doc.created_at)],
    ["Modifié le", formatDateTime(doc.updated_at)],
    ["Antivirus", <StepBadge key="av" status={doc.scan_status} />],
    ["OCR", <StepBadge key="ocr" status={doc.ocr_status} />],
    ["IA", <StepBadge key="ai" status={doc.ai_status} />],
    ["Empreinte SHA-256", <span key="sha" className="break-all font-mono text-[11px]">{doc.sha256}</span>],
  ];
  return (
    <dl className="divide-y px-5">
      {rows.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[130px_1fr] gap-3 py-2.5 text-sm">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="min-w-0">{v}</dd>
        </div>
      ))}
      {doc.duplicate_of_id && (
        <div className="py-3 text-sm">
          <Link to={`/documents/${doc.duplicate_of_id}`} className="text-primary hover:underline">Voir le document original (doublon détecté)</Link>
        </div>
      )}
    </dl>
  );
}

const RELATION_LABELS: Record<string, [string, string]> = {
  split_into: ["Document extrait du lot", "Lot d'origine"],
  copied_to: ["Copie", "Original"],
  parent_of: ["Document enfant", "Document parent"],
  replaces: ["Remplace", "Remplacé par"],
  related: ["Lié", "Lié"],
};

function relationLabel(type: string, direction: string) {
  const pair = RELATION_LABELS[type];
  if (pair) return direction === "outgoing" ? pair[0] : pair[1];
  return `${type} · ${direction === "outgoing" ? "sortante" : "entrante"}`;
}
