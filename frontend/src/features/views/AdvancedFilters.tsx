import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { useDocumentTypes, useObjects } from "@/hooks/queries";
import type { DocumentFilters } from "@/types/api";
import { Button, Field, Input, Select, Switch } from "@/components/ui/primitives";
import { Dialog } from "@/components/ui/overlay";

/** Advanced criteria: owner, tag, dates, linked business object, metadata values. */
export function AdvancedFilters({ open, onOpenChange, value, onApply }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  value: DocumentFilters;
  onApply: (f: DocumentFilters) => void;
}) {
  const { data: types = [] } = useDocumentTypes();
  const [draft, setDraft] = useState<DocumentFilters>(value);
  const [objectSearch, setObjectSearch] = useState("");
  const objects = useObjects({ q: objectSearch || undefined, page_size: 20, status: "active" }, open);
  useEffect(() => {
    if (open) setDraft(value);
  }, [open, value]);

  const type = types.find((t) => t.id === draft.document_type_id);
  const fields = (type ? type.fields : types.flatMap((t) => t.fields)).filter((f) => f.searchable);
  const uniqueFields = [...new Map(fields.map((f) => [f.technical_name, f])).values()];
  const meta = Object.entries(draft.meta ?? {});
  const setMeta = (entries: [string, string][]) => setDraft({ ...draft, meta: Object.fromEntries(entries) });

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Filtres avancés" size="lg"
            footer={<>
              <Button variant="ghost" onClick={() => setDraft({ q: value.q, folder_id: value.folder_id, sort: value.sort, order: value.order, meta: {} })}>Réinitialiser</Button>
              <Button onClick={() => { onApply(draft); onOpenChange(false); }}>Appliquer</Button>
            </>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Type documentaire">
          <Select value={draft.document_type_id ?? ""} onChange={(e) => setDraft({ ...draft, document_type_id: e.target.value || null })}>
            <option value="">Tous</option>
            {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </Field>
        <Field label="Statut">
          <Select value={draft.status ?? ""} onChange={(e) => setDraft({ ...draft, status: (e.target.value || null) as DocumentFilters["status"] })}>
            <option value="">Tous</option>
            <option value="published">Publié</option>
            <option value="pending_validation">À valider</option>
            <option value="processing">En traitement</option>
            <option value="failed">Échec</option>
            <option value="rejected">Rejeté</option>
          </Select>
        </Field>
        <Field label="Déposé à partir du"><Input type="date" value={draft.created_from ?? ""} onChange={(e) => setDraft({ ...draft, created_from: e.target.value || null })} /></Field>
        <Field label="Jusqu'au"><Input type="date" value={draft.created_to ?? ""} onChange={(e) => setDraft({ ...draft, created_to: e.target.value || null })} /></Field>
        <Field label="Tag"><Input value={draft.tag ?? ""} onChange={(e) => setDraft({ ...draft, tag: e.target.value || null })} placeholder="finance" /></Field>
        <Field label="Propriétaire">
          <label className="flex h-9 items-center gap-2 text-sm"><Switch checked={!!draft.mine} onChange={(v) => setDraft({ ...draft, mine: v })} /> Uniquement mes documents</label>
        </Field>
        <div className="sm:col-span-2">
          <Field label="Lié à l'objet métier" hint="Fournisseur, client, projet… (référentiels)">
            <div className="flex gap-2">
              <Input placeholder="Rechercher un objet…" value={objectSearch} onChange={(e) => setObjectSearch(e.target.value)} className="max-w-[220px]" />
              <Select value={draft.object_id ?? ""} onChange={(e) => setDraft({ ...draft, object_id: e.target.value || null })}>
                <option value="">Aucun</option>
                {objects.data?.items.map((o) => <option key={o.id} value={o.id}>{o.object_type.name} · {o.code} — {o.name}</option>)}
                {draft.object_id && !objects.data?.items.some((o) => o.id === draft.object_id) && <option value={draft.object_id}>Objet sélectionné</option>}
              </Select>
            </div>
          </Field>
        </div>
      </div>

      <div className="mt-6">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium">Valeurs de métadonnées</span>
          <Button size="sm" variant="outline" disabled={!uniqueFields.length || meta.length >= 10}
                  onClick={() => setMeta([...meta, [uniqueFields.find((f) => !(f.technical_name in (draft.meta ?? {})))?.technical_name ?? uniqueFields[0].technical_name, ""]])}>
            <Plus /> Ajouter un critère
          </Button>
        </div>
        {meta.length === 0 && <p className="text-xs text-muted-foreground">Ex. « Fournisseur contient Atlas ». Seuls les champs marqués « recherchables » sont proposés.</p>}
        <div className="space-y-2">
          {meta.map(([k, v], i) => (
            <div key={i} className="flex items-center gap-2">
              <Select className="max-w-[240px]" value={k} onChange={(e) => setMeta(meta.map((m, j) => (j === i ? [e.target.value, m[1]] : m)))}>
                {uniqueFields.map((f) => <option key={f.technical_name} value={f.technical_name}>{f.display_name}</option>)}
              </Select>
              <span className="text-xs text-muted-foreground">contient</span>
              <Input value={v} onChange={(e) => setMeta(meta.map((m, j) => (j === i ? [m[0], e.target.value] : m)))} />
              <Button size="icon" variant="ghost" aria-label="Retirer" onClick={() => setMeta(meta.filter((_, j) => j !== i))}><X /></Button>
            </div>
          ))}
        </div>
      </div>
    </Dialog>
  );
}
