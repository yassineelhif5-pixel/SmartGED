import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Boxes, Link2, Plus, Unlink, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useDocumentObjects, useInvalidateDocs, useObjects, useObjectTypes } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { DocumentDetail } from "@/types/api";
import { displayValue } from "@/utils/format";
import { Badge, Button, Field, Input, Select, Spinner, Switch } from "@/components/ui/primitives";
import { Dialog } from "@/components/ui/overlay";

/** Business objects linked to the document: shown as reference properties, usable to fill metadata. */
export function ObjectsPanel({ doc }: { doc: DocumentDetail }) {
  const { data: links, isLoading } = useDocumentObjects(doc.id);
  const { data: types = [] } = useObjectTypes();
  const can = useCan();
  const qc = useQueryClient();
  const invalidate = useInvalidateDocs();
  const [open, setOpen] = useState(false);
  const [typeId, setTypeId] = useState("");
  const [q, setQ] = useState("");
  const [objectId, setObjectId] = useState("");
  const [fill, setFill] = useState(true);
  const [busy, setBusy] = useState(false);
  const candidates = useObjects({ object_type_id: typeId || undefined, q: q || undefined, status: "active", page_size: 50 }, open);
  const editable = can("document:update") && !doc.deleted_at;
  const canFill = can("metadata:update") && !!doc.document_type && !doc.deleted_at;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["document-objects", doc.id] });
    invalidate();
  };

  const run = async (fn: () => Promise<string>) => {
    setBusy(true);
    try {
      toast.success(await fn());
      refresh();
      return true;
    } catch (e) {
      toast.error((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const applyFrom = (id: string, overwrite = false) =>
    run(async () => {
      const r = await api<{ filled: string[]; skipped: string[] }>(`/documents/${doc.id}/apply-object`, { method: "POST", body: { object_id: id, overwrite } });
      return r.filled.length ? `${r.filled.length} métadonnée(s) alimentée(s)${r.skipped.length ? `, ${r.skipped.length} déjà renseignée(s)` : ""}` : "Aucun champ correspondant à remplir";
    });

  const linkNow = async () => {
    const ok = await run(async () => {
      if (fill && canFill) {
        await api(`/documents/${doc.id}/apply-object`, { method: "POST", body: { object_id: objectId } });
        return "Objet lié et métadonnées alimentées";
      }
      await api(`/documents/${doc.id}/objects`, { method: "POST", body: { object_id: objectId, role: "related" } });
      return "Objet lié au document";
    });
    if (ok) {
      setOpen(false);
      setObjectId("");
    }
  };

  if (isLoading) return <div className="p-6"><Spinner /></div>;

  return (
    <div className="h-full overflow-y-auto p-5">
      {editable && (
        <Button size="sm" variant="outline" className="mb-4" onClick={() => setOpen(true)}><Plus /> Lier un objet métier</Button>
      )}
      {!links?.length ? (
        <div className="flex flex-col items-center py-10 text-center text-sm text-muted-foreground">
          <Boxes className="mb-2 size-6" />
          Aucun élément non documentaire lié. Rattachez un fournisseur, un client ou un projet pour l'utiliser comme propriété et alimenter les métadonnées.
        </div>
      ) : (
        <ul className="space-y-3">
          {links.map((lk) => {
            const t = types.find((x) => x.id === lk.object.object_type.id);
            return (
              <li key={lk.id} className="rounded-lg border">
                <div className="flex items-start gap-3 border-b px-3 py-2.5">
                  <span className="mt-1 size-2.5 shrink-0 rounded-full" style={{ background: lk.object.object_type.color ?? "#94a3b8" }} />
                  <div className="min-w-0 flex-1">
                    <Link to={`/objects?type=${lk.object.object_type.id}`} className="block truncate text-sm font-medium hover:text-primary">{lk.object.name}</Link>
                    <div className="text-xs text-muted-foreground">{lk.object.object_type.name} · <span className="font-mono">{lk.object.code}</span></div>
                  </div>
                  <Badge tone="outline">{lk.role === "related" ? "lié" : lk.role === "source" ? "source" : lk.role}</Badge>
                </div>
                <dl className="space-y-1 px-3 py-2 text-xs">
                  {t?.fields.filter((f) => f.visible).map((f) => (
                    <div key={f.technical_name} className="grid grid-cols-[120px_1fr] gap-2">
                      <dt className="text-muted-foreground">{f.display_name}</dt>
                      <dd className="min-w-0 break-words">{f.sensitive ? "••••••" : displayValue(lk.object.attributes[f.technical_name], f.data_type)}</dd>
                    </div>
                  ))}
                </dl>
                <div className="flex flex-wrap gap-1 border-t px-2 py-1.5">
                  {canFill && <Button size="sm" variant="ghost" className="h-7" loading={busy} onClick={() => applyFrom(lk.object.id)}><Wand2 /> Alimenter les métadonnées</Button>}
                  <Button asChild size="sm" variant="ghost" className="h-7"><Link to={`/documents?object=${lk.object.id}`}><Link2 /> {lk.object.document_count} doc(s)</Link></Button>
                  {editable && (
                    <Button size="sm" variant="ghost" className="ml-auto h-7 text-destructive" aria-label="Délier"
                            onClick={() => run(async () => { await api(`/documents/${doc.id}/objects/${lk.id}`, { method: "DELETE" }); return "Lien supprimé"; })}>
                      <Unlink />
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <Dialog open={open} onOpenChange={setOpen} title="Lier un objet métier" size="md"
              footer={<><Button variant="outline" onClick={() => setOpen(false)}>Annuler</Button><Button disabled={!objectId} loading={busy} onClick={linkNow}>Lier</Button></>}>
        <div className="space-y-4">
          <Field label="Type">
            <Select value={typeId} onChange={(e) => { setTypeId(e.target.value); setObjectId(""); }}>
              <option value="">Tous les types</option>
              {types.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </Select>
          </Field>
          <Field label="Rechercher"><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nom ou référence" /></Field>
          <Field label="Objet">
            <Select value={objectId} onChange={(e) => setObjectId(e.target.value)} size={6} className="h-auto">
              {candidates.data?.items.map((o) => <option key={o.id} value={o.id}>{o.object_type.name} · {o.code} — {o.name}</option>)}
            </Select>
          </Field>
          {canFill && (
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={fill} onChange={setFill} /> Alimenter les métadonnées vides avec les attributs de l'objet
            </label>
          )}
        </div>
      </Dialog>
    </div>
  );
}
