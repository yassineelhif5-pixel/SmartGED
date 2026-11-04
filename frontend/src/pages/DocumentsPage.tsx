import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Download, Eye, FileStack, Search, Trash2, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { api, downloadFile } from "@/api/client";
import { useDocuments, useDocumentTypes, useFolders, useInvalidateDocs } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import { Button, Card, EmptyState, Input, Select } from "@/components/ui/primitives";
import { DropdownItem, DropdownSeparator } from "@/components/ui/overlay";
import { DocumentTable, Pagination } from "@/features/DocumentTable";
import { FolderTree } from "@/features/FolderTree";
import { UploadDialog } from "@/features/UploadDialog";

export default function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const can = useCan();
  const invalidate = useInvalidateDocs();
  const { data: types = [] } = useDocumentTypes();
  const { data: folders = [] } = useFolders();

  const folder = params.get("folder");
  const q = params.get("q") ?? "";
  const type = params.get("type") ?? "";
  const status = params.get("status") ?? "";
  const sort = params.get("sort") ?? (q ? "relevance" : "created_at");
  const order = (params.get("order") as "asc" | "desc") ?? "desc";
  const page = Number(params.get("page") ?? 1);
  const [search, setSearch] = useState(q);
  const [uploadOpen, setUploadOpen] = useState(params.get("upload") === "1");

  useEffect(() => setSearch(q), [q]);

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (!("page" in patch)) next.delete("page");
    next.delete("upload");
    setParams(next, { replace: true });
  };

  const { data, isLoading, isFetching } = useDocuments({
    q: q || undefined,
    folder_id: folder ?? undefined,
    recursive: !!folder,
    document_type_id: type || undefined,
    status: status || undefined,
    sort,
    order,
    page,
    page_size: 25,
  });

  const currentFolder = folders.find((f) => f.id === folder);

  const trash = async (id: string) => {
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      toast.success("Document placé dans la corbeille");
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="flex gap-6">
      <aside className="hidden w-60 shrink-0 lg:block">
        <div className="sticky top-0">
          <FolderTree selected={folder} onSelect={(id) => update({ folder: id })} />
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{currentFolder?.name ?? (q ? "Résultats de recherche" : "Tous les documents")}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {data ? `${data.total.toLocaleString("fr-FR")} document(s)` : "Chargement…"}
              {currentFolder && " · sous-dossiers inclus"}
            </p>
          </div>
          {can("document:create") && (
            <Button onClick={() => setUploadOpen(true)}>
              <Upload /> Déposer
            </Button>
          )}
        </div>

        <Card>
          <div className="flex flex-wrap items-center gap-2 border-b p-3">
            <form className="relative min-w-[220px] flex-1" onSubmit={(e) => { e.preventDefault(); update({ q: search.trim() || null, sort: search.trim() ? "relevance" : null }); }}>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 pr-8"
                     placeholder="Rechercher dans le contenu OCR, le titre, le nom de fichier…" aria-label="Rechercher" />
              {q && (
                <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" aria-label="Effacer"
                        onClick={() => update({ q: null, sort: null })}>
                  <X className="size-4" />
                </button>
              )}
            </form>
            <Select className="w-auto min-w-[160px]" value={type} onChange={(e) => update({ type: e.target.value || null })} aria-label="Type">
              <option value="">Tous les types</option>
              {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </Select>
            <Select className="w-auto min-w-[150px]" value={status} onChange={(e) => update({ status: e.target.value || null })} aria-label="Statut">
              <option value="">Tous les statuts</option>
              <option value="published">Publié</option>
              <option value="pending_validation">À valider</option>
              <option value="processing">En traitement</option>
              <option value="failed">Échec</option>
              <option value="rejected">Rejeté</option>
            </Select>
            {isFetching && !isLoading && <span className="text-xs text-muted-foreground">Actualisation…</span>}
          </div>

          {data && data.total === 0 ? (
            <EmptyState
              icon={FileStack}
              title={q ? "Aucun résultat" : "Aucun document ici"}
              description={q ? "Essayez d'autres mots-clés ou retirez des filtres." : "Déposez des fichiers : ils seront analysés et indexés automatiquement."}
              action={!q && can("document:create") ? <Button onClick={() => setUploadOpen(true)}><Upload /> Déposer</Button> : undefined}
            />
          ) : (
            <>
              <DocumentTable
                items={data?.items}
                loading={isLoading}
                sort={sort}
                order={order}
                onSort={(f) => update({ sort: f, order: sort === f && order === "desc" ? "asc" : "desc" })}
                rowActions={(d) => (
                  <>
                    <DropdownItem onSelect={() => navigate(`/documents/${d.id}`)}><Eye /> Ouvrir</DropdownItem>
                    {can("document:download") && (
                      <DropdownItem onSelect={() => downloadFile(`/documents/${d.id}/download`, d.file_name).catch((e) => toast.error(e.message))}>
                        <Download /> Télécharger
                      </DropdownItem>
                    )}
                    {can("document:delete") && (
                      <>
                        <DropdownSeparator />
                        <DropdownItem destructive onSelect={() => trash(d.id)}><Trash2 /> Mettre à la corbeille</DropdownItem>
                      </>
                    )}
                  </>
                )}
              />
              {data && <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={(p) => update({ page: String(p) })} />}
            </>
          )}
        </Card>
      </div>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} defaultFolder={folder} />
    </div>
  );
}
