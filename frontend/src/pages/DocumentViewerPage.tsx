import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Bot, Download, Lock, MoreHorizontal, Pencil, RotateCcw, Scissors, Trash2, Unlock, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, downloadFile } from "@/api/client";
import { useDocument, useDocumentTypes, useFolders, useInvalidateDocs } from "@/hooks/queries";
import { useCan, useSessionStore } from "@/stores/session";
import { cn } from "@/utils/format";
import { Badge, Button, Card, Field, Input, Select, Spinner } from "@/components/ui/primitives";
import { ConfirmDialog, Dialog, DropdownContent, DropdownItem, DropdownMenu, DropdownSeparator, DropdownTrigger } from "@/components/ui/overlay";
import { DocumentStatusBadge } from "@/components/StatusBadge";
import { Preview } from "@/features/viewer/Preview";
import { MetadataPanel } from "@/features/viewer/MetadataPanel";
import { ObjectsPanel } from "@/features/viewer/ObjectsPanel";
import { AIBar } from "@/features/viewer/AIBar";
import { SplitBanner } from "@/features/splitting/SplitBanner";
import { InfoPanel, ProcessingPanel, RelationsPanel, TextPanel, VersionsPanel } from "@/features/viewer/Panels";

const TABS = [
  { id: "metadata", label: "Métadonnées" },
  { id: "objects", label: "Objets liés" },
  { id: "text", label: "Texte" },
  { id: "processing", label: "Traitement" },
  { id: "versions", label: "Versions" },
  { id: "relations", label: "Relations" },
  { id: "info", label: "Infos" },
] as const;

export default function DocumentViewerPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const can = useCan();
  const me = useSessionStore((s) => s.session?.user.id);
  const invalidate = useInvalidateDocs();
  const { data: doc, isLoading, error } = useDocument(id);
  const { data: types = [] } = useDocumentTypes();
  const { data: folders = [] } = useFolders();
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("metadata");
  const [editOpen, setEditOpen] = useState(false);
  const [confirmTrash, setConfirmTrash] = useState(false);
  const [form, setForm] = useState({ title: "", folder: "", type: "", tags: "" });
  const [busy, setBusy] = useState(false);

  if (isLoading) return <div className="flex justify-center py-20"><Spinner className="size-6" /></div>;
  if (error || !doc)
    return (
      <div className="py-20 text-center">
        <p className="text-sm text-muted-foreground">{(error as Error)?.message ?? "Document introuvable"}</p>
        <Button asChild variant="link"><Link to="/documents">Retour aux documents</Link></Button>
      </div>
    );

  const type = types.find((t) => t.id === doc.document_type?.id);
  const lockedByOther = !!doc.checked_out_by && doc.checked_out_by !== me;

  const run = async (fn: () => Promise<unknown>, success: string) => {
    setBusy(true);
    try {
      await fn();
      toast.success(success);
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const openEdit = () => {
    setForm({ title: doc.title, folder: doc.folder_id ?? "", type: doc.document_type?.id ?? "", tags: doc.tags.join(", ") });
    setEditOpen(true);
  };

  const saveEdit = () =>
    run(async () => {
      await api(`/documents/${doc.id}`, {
        method: "PATCH",
        body: {
          title: form.title,
          folder_id: form.folder || null,
          move_to_root: !form.folder,
          document_type_id: form.type || null,
          clear_document_type: !form.type && !!doc.document_type,
          tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        },
      });
      setEditOpen(false);
    }, "Document mis à jour");

  return (
    <div className="-my-2 flex h-[calc(100vh-7rem)] flex-col">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)} aria-label="Retour"><ArrowLeft /></Button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-lg font-semibold tracking-tight">{doc.title}</h1>
            <DocumentStatusBadge status={doc.status} />
            {doc.document_type && (
              <Badge tone="outline">
                <span className="size-2 rounded-full" style={{ background: doc.document_type.color ?? "#94a3b8" }} />
                {doc.document_type.name}
              </Badge>
            )}
            {doc.deleted_at && <Badge tone="red">Dans la corbeille</Badge>}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {doc.original_file_name} · v{doc.current_version}
            {doc.checked_out_by && <span className="text-warning"> · extrait par {doc.checked_out_by_name}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {can("ai_assistant:read") && !doc.deleted_at && (
            <Button variant="outline" size="sm" onClick={() => navigate(`/lina?document=${doc.id}`)}>
              <Bot /> Demander à Lina
            </Button>
          )}
          {can("document:download") && (
            <Button variant="outline" size="sm" onClick={() => downloadFile(`/documents/${doc.id}/download`, doc.file_name).catch((e) => toast.error(e.message))}>
              <Download /> Télécharger
            </Button>
          )}
          {doc.deleted_at ? (
            can("document:delete") && (
              <Button size="sm" loading={busy} onClick={() => run(() => api(`/documents/${doc.id}/restore`, { method: "POST" }), "Document restauré")}>
                <RotateCcw /> Restaurer
              </Button>
            )
          ) : (
            can("document:update") && (
              <>
                <Button variant="outline" size="sm" onClick={openEdit} disabled={lockedByOther}><Pencil /> Modifier</Button>
                <DropdownMenu>
                  <DropdownTrigger asChild>
                    <Button variant="outline" size="icon" className="size-8" aria-label="Plus d'actions"><MoreHorizontal /></Button>
                  </DropdownTrigger>
                  <DropdownContent>
                    {!doc.checked_out_by && (
                      <DropdownItem onSelect={() => run(() => api(`/documents/${doc.id}/checkout`, { method: "POST" }), "Document extrait (verrouillé)")}>
                        <Lock /> Extraire (check-out)
                      </DropdownItem>
                    )}
                    {doc.checked_out_by && (
                      <DropdownItem
                        disabled={lockedByOther && !can("tenant_settings:administer")}
                        onSelect={() => run(() => api(`/documents/${doc.id}/checkin`, { method: "POST", query: { force: lockedByOther } }), "Document libéré")}
                      >
                        <Unlock /> Libérer (check-in)
                      </DropdownItem>
                    )}
                    {can("document:create") && doc.mime_type === "application/pdf" && (doc.page_count ?? 0) > 1
                      && !doc.parent_document_id && doc.status !== "archived" && (
                      <DropdownItem onSelect={() => navigate(`/documents/${doc.id}/split`)}>
                        <Scissors /> Découper le PDF
                      </DropdownItem>
                    )}
                    {can("document:validate") && doc.status === "pending_validation" && (
                      <DropdownItem onSelect={() => run(() => api(`/documents/${doc.id}/reject`, { method: "POST" }), "Document rejeté")}>
                        <XCircle /> Rejeter
                      </DropdownItem>
                    )}
                    {can("document:delete") && (
                      <>
                        <DropdownSeparator />
                        <DropdownItem destructive disabled={lockedByOther} onSelect={() => setConfirmTrash(true)}>
                          <Trash2 /> Mettre à la corbeille
                        </DropdownItem>
                      </>
                    )}
                  </DropdownContent>
                </DropdownMenu>
              </>
            )
          )}
        </div>
      </div>

      {!doc.deleted_at && <SplitBanner doc={doc} />}
      {!doc.deleted_at && <AIBar doc={doc} />}
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <Card className="min-h-[50vh] overflow-hidden">
          <Preview doc={doc} version={doc.current_version} />
        </Card>
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <div className="flex gap-1 overflow-x-auto border-b px-2" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "whitespace-nowrap border-b-2 px-3 py-2.5 text-xs font-medium transition-colors",
                  tab === t.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1">
            {tab === "metadata" && <MetadataPanel doc={doc} type={type} />}
            {tab === "objects" && <ObjectsPanel doc={doc} />}
            {tab === "text" && <TextPanel doc={doc} />}
            {tab === "processing" && <ProcessingPanel doc={doc} />}
            {tab === "versions" && <VersionsPanel doc={doc} />}
            {tab === "relations" && <RelationsPanel doc={doc} />}
            {tab === "info" && <div className="h-full overflow-y-auto"><InfoPanel doc={doc} /></div>}
          </div>
        </Card>
      </div>

      <Dialog open={editOpen} onOpenChange={setEditOpen} title="Modifier le document"
              footer={<><Button variant="outline" onClick={() => setEditOpen(false)}>Annuler</Button><Button loading={busy} onClick={saveEdit}>Enregistrer</Button></>}>
        <div className="space-y-4">
          <Field label="Titre"><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} maxLength={500} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Dossier">
              <Select value={form.folder} onChange={(e) => setForm({ ...form, folder: e.target.value })}>
                <option value="">Racine</option>
                {folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </Select>
            </Field>
            <Field label="Type documentaire">
              <Select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                <option value="">Non classé</option>
                {types.filter((t) => t.is_active || t.id === form.type).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Tags" hint="Séparés par des virgules"><Input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} /></Field>
        </div>
      </Dialog>
      <ConfirmDialog open={confirmTrash} onOpenChange={setConfirmTrash} title="Mettre à la corbeille ?" destructive loading={busy}
                     description="Le document restera récupérable depuis la corbeille."
                     confirmLabel="Mettre à la corbeille"
                     onConfirm={() => run(async () => { await api(`/documents/${doc.id}`, { method: "DELETE" }); setConfirmTrash(false); navigate("/documents"); }, "Document placé dans la corbeille")} />
    </div>
  );
}
