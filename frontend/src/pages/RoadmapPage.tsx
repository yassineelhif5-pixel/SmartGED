import { CheckCircle2, CircleDashed } from "lucide-react";
import { Badge, Card, PageHeader } from "@/components/ui/primitives";

/** Honest product status: what is live in this build and what is coming next. */
const PHASES = [
  { id: "foundation", name: "Phase 1 — Fondations", done: true, items: ["Multi-tenant + RLS PostgreSQL", "Authentification JWT + refresh rotatif", "RBAC granulaire", "Audit chaîné", "Design system"] },
  { id: "ecm", name: "Phase 2 — GED cœur", done: true, items: ["Vues partagées et personnelles", "Référentiels (objets métier)", "Dossiers, documents, versions", "Check-in / check-out", "Corbeille", "Types documentaires & métadonnées", "OCR Tesseract réel", "Recherche plein texte", "Validation humaine"] },
  { id: "ai", name: "Phase 3 — Intelligence IA", done: true, items: ["Fournisseurs IA multi-provider (clés chiffrées, secours)", "Classification automatique", "Extraction des métadonnées avec score de confiance", "Prompt Studio versionné", "Crédits et consommation IA"] },
  { id: "split", name: "Phase 3b — Découpage documentaire", done: false, items: ["Détection des frontières dans un PDF multi-documents", "Interface de validation du découpage"] },
  { id: "search", name: "Phase 4 — Recherche intelligente & Lina", done: false, items: ["Embeddings pgvector", "Recherche hybride", "RAG avec contrôle des permissions", "Assistant Lina"] },
  { id: "workflows", name: "Phase 5 — Workflows", done: false, items: ["Designer React Flow", "Moteur d'exécution", "Approbations", "Notifications"] },
  { id: "ingestion", name: "Phase 6 — Ingestion Hub", done: false, items: ["SharePoint / OneDrive", "E-mail", "S3 / Azure Blob", "SFTP", "Webhooks"] },
  { id: "saas", name: "Phase 7-8 — SaaS & reporting", done: false, items: ["Licences", "Crédits IA", "SSO Entra ID / SAML", "Exports Excel/PDF"] },
];

export default function RoadmapPage() {
  return (
    <>
      <PageHeader title="Feuille de route produit" description="Modules disponibles dans cette version et modules à venir. Aucune fonctionnalité n'est simulée." />
      <div className="grid gap-4 md:grid-cols-2">
        {PHASES.map((p) => (
          <Card key={p.id} id={p.id} className="p-5">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{p.name}</h3>
              <Badge tone={p.done ? "green" : "neutral"}>{p.done ? "Disponible" : "À venir"}</Badge>
            </div>
            <ul className="mt-3 space-y-1.5 text-sm">
              {p.items.map((i) => (
                <li key={i} className="flex items-center gap-2">
                  {p.done ? <CheckCircle2 className="size-4 text-success" /> : <CircleDashed className="size-4 text-muted-foreground" />}
                  {i}
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </>
  );
}
