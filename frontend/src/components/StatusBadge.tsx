import { CheckCircle2, CircleDashed, CircleSlash, Loader2, XCircle, MinusCircle } from "lucide-react";
import { Badge } from "@/components/ui/primitives";
import type { DocumentStatus, StepStatus } from "@/types/api";

const DOC: Record<DocumentStatus, { label: string; tone: "neutral" | "blue" | "green" | "amber" | "red" }> = {
  uploaded: { label: "Déposé", tone: "neutral" },
  processing: { label: "En traitement", tone: "blue" },
  pending_validation: { label: "À valider", tone: "amber" },
  published: { label: "Publié", tone: "green" },
  rejected: { label: "Rejeté", tone: "red" },
  archived: { label: "Archivé", tone: "neutral" },
  failed: { label: "Échec", tone: "red" },
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const s = DOC[status];
  return (
    <Badge tone={s.tone}>
      {status === "processing" && <Loader2 className="size-3 animate-spin" />}
      {s.label}
    </Badge>
  );
}

const STEP: Record<StepStatus, { label: string; tone: "neutral" | "blue" | "green" | "amber" | "red"; icon: typeof CheckCircle2 }> = {
  pending: { label: "En attente", tone: "neutral", icon: CircleDashed },
  running: { label: "En cours", tone: "blue", icon: Loader2 },
  completed: { label: "Terminé", tone: "green", icon: CheckCircle2 },
  failed: { label: "Échec", tone: "red", icon: XCircle },
  skipped: { label: "Ignoré", tone: "neutral", icon: MinusCircle },
  not_configured: { label: "Non configuré", tone: "amber", icon: CircleSlash },
};

export function StepBadge({ status }: { status: StepStatus }) {
  const s = STEP[status];
  const Icon = s.icon;
  return (
    <Badge tone={s.tone}>
      <Icon className={`size-3 ${status === "running" ? "animate-spin" : ""}`} />
      {s.label}
    </Badge>
  );
}

export const STEP_LABELS: Record<string, string> = {
  antivirus: "Contrôle antivirus",
  text_extraction: "OCR & extraction du texte",
  language: "Détection de la langue",
  classification: "Classification IA",
  metadata_extraction: "Extraction des métadonnées",
  indexing: "Indexation",
  publication: "Publication",
};
