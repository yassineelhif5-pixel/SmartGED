import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Archive, Boxes, FileStack, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { useObjects, useObjectTypes } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { BusinessObject, ObjectType } from "@/types/api";
import { cn, displayValue, formatDateTime } from "@/utils/format";
import { Badge, Button, Card, CardHeader, EmptyState, Field, Input, PageHeader, Select, Textarea } from "@/components/ui/primitives";
import { ConfirmDialog, Dialog } from "@/components/ui/overlay";
import { Pagination } from "@/features/DocumentTable";
import { FieldEditor } from "@/features/objects/FieldEditor";

type Form = { id?: string; object_type_id: string; code: string; name: string; description: string; status: "active" | "archived"; attributes: Record<string, unknown> };

/** Référentiels: non-document business objects that feed documents and serve as reference properties. */
export default function ObjectsPage() {
  const { data: types = [] } = useObjectTypes();
  const [params, setParams] = useSearchParams();
  const can = useCan();
  const qc = useQueryClient();
  const typeId = params.get("type") ?? types.find((t) => t.is_active)?.id ?? "";
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"active" | "archived" | "">("active");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<BusinessObject | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [toDelete, setToDelete] = useState<BusinessObject | null>(null);
  const [busy, setBusy] = useState(false);
  const type = types.find((t) => t.id === typeId);
  const { data, isLoading } = useObjects({ object_type_id: typeId || undefined, q: q || undefined, status: status || undefined, page, page_size: 25 }, !!typeId);

  useEffect(() => setSelected(null), [typeId]);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["objects"] });
    qc.invalidateQueries({ queryKey: ["object-types"] });
  };

  const openForm = (obj?: BusinessObject) =>
    setForm(obj
      ? { id: obj.id, object_type_id: obj.object_type.id, code: obj.code, name: obj.name, description: obj.description ?? "", status: obj.status, attributes: { ...obj.attributes } }
      : { object_type_id: typeId, code: "", name: "", description: "", status: "active", attributes: {} });

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setErrors({});
    try {
      const saved = await api<BusinessObject>(form.id ? `/objects/${form.id}` : "/objects", {
        method: form.id ? "PUT" : "POST",
        body: { ...form, description: form.description || null },
      });
      toast.success(form.id ? "Objet mis à jour" : "Objet créé");
      setForm(null);
      setSelected(saved);
      refresh();
    } catch (e) {
      if (e instanceof ApiError && Array.isArray(e.details))
        setErrors(Object.fromEntries((e.details as { field?: string; message?: string }[]).filter((d) => d.field).map((d) => [d.field!, d.message ?? "invalide"])));
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!toDelete) return;
    setBusy(true);
    try {
      const r = await api<{ message: string }>(`/objects/${toDelete.id}`, { method: "DELETE" });
      toast.success(r.message);
      setToDelete(null);
      setSelected(null);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const formType: ObjectType | undefined = types.find((t) => t.id === form?.object_type_id);

  return (
    <>
      <PageHeader title="Référentiels" description="Éléments non documentaires — fournisseurs, clients, projets… — utilisés comme propriétés de référence et pour alimenter les métadonnées des documents."
                  actions={can("business_object:create") && type?.is_active && <Button onClick={() => openForm()}><Plus /> Nouveau {type.name.toLowerCase()}</Button>} />

      {types.length === 0 ? (
        <Card><EmptyState icon={Boxes} title="Aucun type d'objet" description="Un administrateur doit d'abord définir les types d'objets (Administration → Types d'objets)." /></Card>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {types.map((t) => (
              <button key={t.id} onClick={() => { setParams({ type: t.id }, { replace: true }); setPage(1); }}
                      className={cn("inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm", t.id === typeId ? "border-primary bg-accent font-medium" : "bg-card hover:bg-muted", !t.is_active && "opacity-60")}>
                <span className="size-2.5 rounded-full" style={{ background: t.color ?? "#94a3b8" }} />
                {t.name} <span className="text-xs text-muted-foreground">{t.object_count}</span>
              </button>
            ))}
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_400px]">
            <Card>
              <div className="flex flex-wrap gap-2 border-b p-3">
                <div className="relative min-w-[220px] flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input className="pl-9" placeholder="Rechercher par nom ou référence…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label="Rechercher un objet" />
                </div>
                <Select className="w-auto" value={status} onChange={(e) => { setStatus(e.target.value as typeof status); setPage(1); }} aria-label="Statut">
                  <option value="active">Actifs</option>
                  <option value="archived">Archivés</option>
                  <option value="">Tous</option>
                </Select>
              </div>
              {data?.total === 0 ? (
                <EmptyState icon={Boxes} title={q ? "Aucun résultat" : `Aucun ${type?.name.toLowerCase() ?? "objet"}`}
                            description="Créez des fiches pour pouvoir les rattacher à vos documents." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
                      <tr>
                        <th className="px-4 py-2.5 text-left font-medium">Référence</th>
                        <th className="px-4 py-2.5 text-left font-medium">Nom</th>
                        {type?.fields.filter((f) => f.visible && !f.sensitive).slice(0, 2).map((f) => (
                          <th key={f.technical_name} className="hidden px-4 py-2.5 text-left font-medium lg:table-cell">{f.display_name}</th>
                        ))}
                        <th className="px-4 py-2.5 text-right font-medium">Documents</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {isLoading && !data && <tr><td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">Chargement…</td></tr>}
                      {data?.items.map((o) => (
                        <tr key={o.id} onClick={() => setSelected(o)} className={cn("cursor-pointer hover:bg-muted/40", selected?.id === o.id && "bg-accent/50")}>
                          <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">{o.code}</td>
                          <td className="px-4 py-2.5 font-medium">{o.name} {o.status === "archived" && <Badge tone="neutral">archivé</Badge>}</td>
                          {type?.fields.filter((f) => f.visible && !f.sensitive).slice(0, 2).map((f) => (
                            <td key={f.technical_name} className="hidden max-w-[200px] truncate px-4 py-2.5 text-muted-foreground lg:table-cell">{displayValue(o.attributes[f.technical_name], f.data_type)}</td>
                          ))}
                          <td className="tabular px-4 py-2.5 text-right">{o.document_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {data && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
            </Card>

            <Card className="h-fit">
              {selected ? (
                <>
                  <CardHeader title={selected.name} description={`${selected.object_type.name} · ${selected.code}`}
                              actions={<div className="flex gap-1">
                                {can("business_object:update") && <Button size="icon" variant="ghost" aria-label="Modifier" onClick={() => openForm(selected)}><Pencil /></Button>}
                                {can("business_object:delete") && <Button size="icon" variant="ghost" aria-label="Supprimer" onClick={() => setToDelete(selected)}><Trash2 className="text-destructive" /></Button>}
                              </div>} />
                  <dl className="divide-y px-5">
                    {selected.description && <p className="py-3 text-sm text-muted-foreground">{selected.description}</p>}
                    {type?.fields.map((f) => (
                      <div key={f.technical_name} className="grid grid-cols-[140px_1fr] gap-3 py-2.5 text-sm">
                        <dt className="text-muted-foreground">{f.display_name}</dt>
                        <dd className="min-w-0 break-words">{f.sensitive ? "••••••" : displayValue(selected.attributes[f.technical_name], f.data_type)}</dd>
                      </div>
                    ))}
                    <div className="py-2.5 text-xs text-muted-foreground">Modifié le {formatDateTime(selected.updated_at)}</div>
                  </dl>
                  <div className="border-t p-4">
                    <Button asChild variant="outline" size="sm" className="w-full">
                      <Link to={`/documents?object=${selected.id}`}><FileStack /> Voir les {selected.document_count} document(s) liés</Link>
                    </Button>
                  </div>
                </>
              ) : (
                <EmptyState icon={Archive} title="Sélectionnez une fiche" description="Ses propriétés et les documents qui y sont rattachés s'afficheront ici." />
              )}
            </Card>
          </div>
        </>
      )}

      <Dialog open={!!form} onOpenChange={(o) => !o && setForm(null)} title={form?.id ? "Modifier la fiche" : `Nouveau ${formType?.name.toLowerCase() ?? "objet"}`} size="lg"
              footer={<><Button variant="outline" onClick={() => setForm(null)}>Annuler</Button><Button loading={busy} disabled={!form?.code || !form?.name} onClick={save}>Enregistrer</Button></>}>
        {form && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Référence" hint="Identifiant unique, ex. FRN-0042"><Input value={form.code} maxLength={80} onChange={(e) => setForm({ ...form, code: e.target.value })} className="font-mono" /></Field>
            <Field label="Nom"><Input value={form.name} maxLength={300} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            {formType?.fields.map((f) => (
              <div key={f.technical_name} className={f.data_type === "long_text" ? "sm:col-span-2" : undefined}>
                <Field label={`${f.display_name}${f.required ? " *" : ""}`} error={errors[f.technical_name]} hint={f.description ?? undefined}>
                  <FieldEditor def={f} value={form.attributes[f.technical_name]} onChange={(v) => setForm({ ...form, attributes: { ...form.attributes, [f.technical_name]: v } })} />
                </Field>
              </div>
            ))}
            <div className="sm:col-span-2"><Field label="Description"><Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field></div>
            {form.id && (
              <Field label="Statut">
                <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as Form["status"] })}>
                  <option value="active">Actif</option><option value="archived">Archivé</option>
                </Select>
              </Field>
            )}
          </div>
        )}
      </Dialog>
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} destructive loading={busy} confirmLabel="Supprimer"
                     title="Supprimer la fiche ?" onConfirm={remove}
                     description="Si des documents y sont rattachés, la fiche sera archivée au lieu d'être supprimée (les liens restent consultables)." />
    </>
  );
}
