import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Shapes, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { useDocumentTypes } from "@/hooks/queries";
import { useQueryClient } from "@tanstack/react-query";
import { useCan } from "@/stores/session";
import type { DataType, DocumentType, MetadataField } from "@/types/api";
import { cn } from "@/utils/format";
import { Badge, Button, Card, EmptyState, Field, Input, PageHeader, Select, Switch, Textarea } from "@/components/ui/primitives";

const DATA_TYPES: { value: DataType; label: string }[] = [
  { value: "text", label: "Texte" },
  { value: "long_text", label: "Texte long" },
  { value: "integer", label: "Entier" },
  { value: "decimal", label: "Décimal" },
  { value: "currency", label: "Montant" },
  { value: "date", label: "Date" },
  { value: "datetime", label: "Date et heure" },
  { value: "boolean", label: "Oui / Non" },
  { value: "dropdown", label: "Liste" },
  { value: "multi_select", label: "Choix multiple" },
  { value: "reference", label: "Référence" },
];

type Draft = Omit<DocumentType, "id" | "schema_version" | "document_count"> & { id?: string };

const emptyField = (): MetadataField => ({
  technical_name: "", display_name: "", data_type: "text", required: false, validation_rules: {}, allowed_values: null,
  searchable: true, visible: true, ai_extraction_enabled: true, sensitive: false, requires_human_validation: false,
  description: null, extraction_prompt: null,
});

const slugify = (s: string) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^(\d)/, "f_$1").slice(0, 60);

export default function DocumentTypesPage() {
  const { data: types = [], isLoading } = useDocumentTypes();
  const qc = useQueryClient();
  const can = useCan();
  const [selected, setSelected] = useState<string | "new" | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const editable = can("document_type:update") || (selected === "new" && can("document_type:create"));

  useEffect(() => {
    if (selected === null && types.length) setSelected(types[0].id);
  }, [types, selected]);

  useEffect(() => {
    if (selected === "new")
      setDraft({ code: "", name: "", description: "", color: "#2563eb", icon: null, requires_validation: false, classification_hints: "", is_active: true, fields: [] });
    else {
      const t = types.find((x) => x.id === selected);
      if (t) setDraft(structuredClone(t));
    }
  }, [selected, types]);

  const setField = (i: number, patch: Partial<MetadataField>) =>
    setDraft((d) => d && { ...d, fields: d.fields.map((f, j) => (j === i ? { ...f, ...patch } : f)) });
  const move = (i: number, dir: -1 | 1) =>
    setDraft((d) => {
      if (!d) return d;
      const fields = [...d.fields];
      const [x] = fields.splice(i, 1);
      fields.splice(i + dir, 0, x);
      return { ...d, fields };
    });

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    const body = {
      ...draft,
      code: draft.code || slugify(draft.name),
      fields: draft.fields.map(({ position: _p, ...f }) => ({
        ...f,
        technical_name: f.technical_name || slugify(f.display_name),
        allowed_values: f.data_type === "dropdown" || f.data_type === "multi_select" ? f.allowed_values ?? [] : null,
      })),
    };
    try {
      const saved = await api<DocumentType>(selected === "new" ? "/document-types" : `/document-types/${selected}`, {
        method: selected === "new" ? "POST" : "PUT",
        body,
      });
      await qc.invalidateQueries({ queryKey: ["document-types"] });
      setSelected(saved.id);
      toast.success(`Type enregistré — schéma v${saved.schema_version}`);
    } catch (e) {
      const details = e instanceof ApiError && Array.isArray(e.details) ? ` (${(e.details as { loc: string[] }[]).map((d) => d.loc.slice(-2).join(".")).join(", ")})` : "";
      toast.error((e as Error).message + details);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!selected || selected === "new") return;
    try {
      const r = await api<{ message: string }>(`/document-types/${selected}`, { method: "DELETE" });
      toast.success(r.message);
      setSelected(null);
      qc.invalidateQueries({ queryKey: ["document-types"] });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
      <PageHeader title="Types documentaires" description="Définissez vos types de documents et leurs métadonnées — sans développement. Chaque modification structurelle crée une nouvelle version du schéma."
        actions={can("document_type:create") && <Button onClick={() => setSelected("new")}><Plus /> Nouveau type</Button>} />
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <Card className="h-fit p-2">
          {isLoading ? null : types.length === 0 && selected !== "new" ? (
            <EmptyState icon={Shapes} title="Aucun type" />
          ) : (
            <ul>
              {types.map((t) => (
                <li key={t.id}>
                  <button onClick={() => setSelected(t.id)}
                          className={cn("flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm", selected === t.id ? "bg-accent" : "hover:bg-muted")}>
                    <span className="size-3 rounded-full" style={{ background: t.color ?? "#94a3b8" }} />
                    <span className="min-w-0 flex-1">
                      <span className={cn("block truncate font-medium", !t.is_active && "text-muted-foreground line-through")}>{t.name}</span>
                      <span className="text-xs text-muted-foreground">{t.fields.length} champs · {t.document_count} docs · v{t.schema_version}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {draft && (
          <div className="space-y-6">
            <Card className="p-5">
              <div className="grid gap-4 md:grid-cols-[1fr_1fr_120px]">
                <Field label="Nom"><Input value={draft.name} disabled={!editable} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
                <Field label="Code technique" hint="Généré depuis le nom si vide">
                  <Input value={draft.code} disabled={!editable} placeholder={slugify(draft.name)} onChange={(e) => setDraft({ ...draft, code: e.target.value })} className="font-mono text-xs" />
                </Field>
                <Field label="Couleur"><Input type="color" value={draft.color ?? "#2563eb"} disabled={!editable} onChange={(e) => setDraft({ ...draft, color: e.target.value })} className="h-9 p-1" /></Field>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <Field label="Description"><Textarea rows={2} value={draft.description ?? ""} disabled={!editable} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
                <Field label="Indices de classification IA" hint="Utilisés par le classifieur (phase 3)">
                  <Textarea rows={2} value={draft.classification_hints ?? ""} disabled={!editable} onChange={(e) => setDraft({ ...draft, classification_hints: e.target.value })} />
                </Field>
              </div>
              <div className="mt-4 flex flex-wrap gap-6 text-sm">
                <label className="flex items-center gap-2"><Switch checked={draft.requires_validation} disabled={!editable} onChange={(v) => setDraft({ ...draft, requires_validation: v })} /> Validation humaine requise</label>
                <label className="flex items-center gap-2"><Switch checked={draft.is_active} disabled={!editable} onChange={(v) => setDraft({ ...draft, is_active: v })} /> Actif</label>
              </div>
            </Card>

            <Card>
              <div className="flex items-center justify-between border-b px-5 py-3">
                <h3 className="text-sm font-semibold">Métadonnées <span className="font-normal text-muted-foreground">({draft.fields.length})</span></h3>
                {editable && <Button size="sm" variant="outline" onClick={() => setDraft({ ...draft, fields: [...draft.fields, emptyField()] })}><Plus /> Ajouter un champ</Button>}
              </div>
              <ul className="divide-y">
                {draft.fields.map((f, i) => (
                  <li key={f.id ?? `new-${i}`} className="space-y-3 px-5 py-4">
                    <div className="grid gap-3 md:grid-cols-[1fr_1fr_160px_auto]">
                      <Input placeholder="Libellé" value={f.display_name} disabled={!editable} onChange={(e) => setField(i, { display_name: e.target.value })} />
                      <Input placeholder={slugify(f.display_name) || "nom_technique"} value={f.technical_name} disabled={!editable} className="font-mono text-xs"
                             onChange={(e) => setField(i, { technical_name: e.target.value })} />
                      <Select value={f.data_type} disabled={!editable} onChange={(e) => setField(i, { data_type: e.target.value as DataType })}>
                        {DATA_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                      </Select>
                      {editable && (
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" aria-label="Monter" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp /></Button>
                          <Button variant="ghost" size="icon" aria-label="Descendre" disabled={i === draft.fields.length - 1} onClick={() => move(i, 1)}><ArrowDown /></Button>
                          <Button variant="ghost" size="icon" aria-label="Supprimer le champ" onClick={() => setDraft({ ...draft, fields: draft.fields.filter((_, j) => j !== i) })}><Trash2 className="text-destructive" /></Button>
                        </div>
                      )}
                    </div>
                    {(f.data_type === "dropdown" || f.data_type === "multi_select") && (
                      <Input placeholder="Valeurs autorisées, séparées par des virgules" disabled={!editable}
                             value={(f.allowed_values ?? []).join(", ")}
                             onChange={(e) => setField(i, { allowed_values: e.target.value.split(",").map((v) => v.trim()).filter(Boolean) })} />
                    )}
                    <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs">
                      {([
                        ["required", "Obligatoire"], ["searchable", "Recherchable"], ["visible", "Visible"],
                        ["ai_extraction_enabled", "Extraction IA"], ["sensitive", "Sensible"], ["requires_human_validation", "Validation humaine"],
                      ] as const).map(([k, label]) => (
                        <label key={k} className="flex items-center gap-1.5">
                          <Switch checked={!!f[k]} disabled={!editable} onChange={(v) => setField(i, { [k]: v } as Partial<MetadataField>)} /> {label}
                        </label>
                      ))}
                      {f.sensitive && <Badge tone="amber">Masqué par défaut</Badge>}
                    </div>
                    {f.ai_extraction_enabled && (
                      <Textarea rows={2} placeholder="Consigne d'extraction IA (optionnelle) — ex. « numéro commençant par FA- en haut à droite »" disabled={!editable}
                                value={f.extraction_prompt ?? ""} onChange={(e) => setField(i, { extraction_prompt: e.target.value })} className="text-xs" />
                    )}
                  </li>
                ))}
                {draft.fields.length === 0 && <li className="px-5 py-8 text-center text-sm text-muted-foreground">Aucun champ défini.</li>}
              </ul>
            </Card>

            {editable && (
              <div className="flex justify-between">
                {selected !== "new" && can("document_type:delete") ? (
                  <Button variant="ghost" className="text-destructive" onClick={remove}><Trash2 /> Supprimer</Button>
                ) : <span />}
                <Button onClick={save} loading={saving} disabled={!draft.name}>Enregistrer le type</Button>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
