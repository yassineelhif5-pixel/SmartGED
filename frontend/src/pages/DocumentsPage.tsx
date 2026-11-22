import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Download, Eye, FileStack, Search, SlidersHorizontal, Trash2, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { api, downloadFile } from "@/api/client";
import { useDocuments, useDocumentTypes, useFolders, useInvalidateDocs, useObjects, useViews } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { DocumentFilters, DocumentView } from "@/types/api";
import { Badge, Button, Card, EmptyState, Input, Select } from "@/components/ui/primitives";
import { DropdownItem, DropdownSeparator } from "@/components/ui/overlay";
import { DocumentTable, Pagination } from "@/features/DocumentTable";
import { FolderTree } from "@/features/FolderTree";
import { UploadDialog } from "@/features/UploadDialog";
import { ViewsBar } from "@/features/views/ViewsBar";
import { AdvancedFilters } from "@/features/views/AdvancedFilters";
import { countFilters, filtersFromParams, hasActiveFilters, paramsFromFilters } from "@/features/views/filters";

const STATUS_LABELS: Record<string, string> = {
  published: "Publié", pending_validation: "À valider", processing: "En traitement", failed: "Échec", rejected: "Rejeté",
};

export default function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const can = useCan();
  const invalidate = useInvalidateDocs();
  const { data: types = [] } = useDocumentTypes();
  const { data: folders = [] } = useFolders();
  const views = useViews();

  const filters = useMemo(() => filtersFromParams(params), [params]);
  const viewId = params.get("view");
  const page = Number(params.get("page") ?? 1);
  const [search, setSearch] = useState(filters.q ?? "");
  const [uploadOpen, setUploadOpen] = useState(params.get("upload") === "1");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const defaultApplied = useRef(false);

  useEffect(() => setSearch(filters.q ?? ""), [filters.q]);

  // Open the user's (or the organisation's) default view when arriving without explicit filters.
  useEffect(() => {
    if (defaultApplied.current || !views.data) return;
    defaultApplied.current = true;
    if (hasActiveFilters(params) || viewId || params.get("upload")) return;
    const def = views.data.views.find((v) => v.id === views.data.default_view_id);
    if (def) setParams(paramsFromFilters(def.filters, def.id), { replace: true });
  }, [views.data, params, viewId, setParams]);

  const setFilters = (patch: Partial<DocumentFilters>, keepPage = false) => {
    const next = paramsFromFilters({ ...filters, ...patch }, viewId);
    if (keepPage && params.get("page")) next.set("page", params.get("page")!);
    setParams(next, { replace: true });
  };
  const applyView = (v: DocumentView | null) =>
    setParams(v ? paramsFromFilters(v.filters, v.id) : new URLSearchParams(), { replace: true });

  const { data, isLoading, isFetching } = useDocuments({
    q: filters.q || undefined,
    folder_id: filters.folder_id ?? undefined,
    recursive: !!filters.folder_id,
    document_type_id: filters.document_type_id || undefined,
    status: filters.status || undefined,
    tag: filters.tag || undefined,
    mine: filters.mine || undefined,
    object_id: filters.object_id || undefined,
    created_from: filters.created_from || undefined,
    created_to: filters.created_to ? `${filters.created_to}T23:59:59` : undefined,
    meta: Object.entries(filters.meta ?? {}).map(([k, v]) => `${k}:${v}`),
    sort: filters.sort,
    order: filters.order,
    page,
    page_size: 25,
  });

  const linkedObject = useObjects({ q: undefined, page_size: 200 }, !!filters.object_id);
  const objectLabel = linkedObject.data?.items.find((o) => o.id === filters.object_id);
  const currentFolder = folders.find((f) => f.id === filters.folder_id);
  const activeView = views.data?.views.find((v) => v.id === viewId);
  const fieldLabel = (tech: string) => types.flatMap((t) => t.fields).find((f) => f.technical_name === tech)?.display_name ?? tech;

  const chips: { label: string; clear: Partial<DocumentFilters> }[] = [];
  if (filters.tag) chips.push({ label: `#${filters.tag}`, clear: { tag: null } });
  if (filters.mine) chips.push({ label: "Mes documents", clear: { mine: false } });
  if (filters.object_id) chips.push({ label: `Objet : ${objectLabel ? `${objectLabel.code} — ${objectLabel.name}` : "sélectionné"}`, clear: { object_id: null } });
  if (filters.created_from) chips.push({ label: `Depuis le ${filters.created_from}`, clear: { created_from: null } });
  if (filters.created_to) chips.push({ label: `Jusqu'au ${filters.created_to}`, clear: { created_to: null } });
  Object.entries(filters.meta ?? {}).forEach(([k, v]) => {
    const rest = { ...filters.meta };
    delete rest[k];
    chips.push({ label: `${fieldLabel(k)} ∋ ${v}`, clear: { meta: rest } });
  });

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
          <FolderTree selected={filters.folder_id ?? null} onSelect={(id) => setFilters({ folder_id: id })} />
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              {activeView?.name ?? currentFolder?.name ?? (filters.q ? "Résultats de recherche" : "Tous les documents")}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {data ? `${data.total.toLocaleString("fr-FR")} document(s)` : "Chargement…"}
              {currentFolder && ` · dossier « ${currentFolder.name} », sous-dossiers inclus`}
              {activeView && (activeView.scope === "tenant" ? " · vue partagée" : " · vue personnelle")}
            </p>
          </div>
          {can("document:create") && (
            <Button onClick={() => setUploadOpen(true)}>
              <Upload /> Déposer
            </Button>
          )}
        </div>

        <ViewsBar activeViewId={viewId} current={filters} onApply={applyView} />

        <Card>
          <div className="flex flex-wrap items-center gap-2 border-b p-3">
            <form className="relative min-w-[220px] flex-1" onSubmit={(e) => { e.preventDefault(); setFilters({ q: search.trim() || null, sort: search.trim() ? "relevance" : "created_at" }); }}>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 pr-8"
                     placeholder="Rechercher dans le contenu OCR, le titre, le nom de fichier…" aria-label="Rechercher" />
              {filters.q && (
                <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" aria-label="Effacer"
                        onClick={() => setFilters({ q: null, sort: "created_at" })}>
                  <X className="size-4" />
                </button>
              )}
            </form>
            <Select className="w-auto min-w-[160px]" value={filters.document_type_id ?? ""} onChange={(e) => setFilters({ document_type_id: e.target.value || null })} aria-label="Type">
              <option value="">Tous les types</option>
              {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </Select>
            <Select className="w-auto min-w-[150px]" value={filters.status ?? ""} onChange={(e) => setFilters({ status: (e.target.value || null) as DocumentFilters["status"] })} aria-label="Statut">
              <option value="">Tous les statuts</option>
              {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
            <Button variant="outline" onClick={() => setAdvancedOpen(true)}>
              <SlidersHorizontal /> Filtres
              {countFilters(filters) > 0 && <Badge tone="blue">{countFilters(filters)}</Badge>}
            </Button>
            {isFetching && !isLoading && <span className="text-xs text-muted-foreground">Actualisation…</span>}
          </div>
          {chips.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-3 py-2">
              {chips.map((c) => (
                <span key={c.label} className="inline-flex items-center gap-1 rounded-full border bg-card px-2.5 py-0.5 text-xs">
                  {c.label}
                  <button aria-label={`Retirer ${c.label}`} onClick={() => setFilters(c.clear)}><X className="size-3" /></button>
                </span>
              ))}
              <button className="text-xs text-primary hover:underline"
                      onClick={() => setFilters({ tag: null, mine: false, object_id: null, created_from: null, created_to: null, meta: {} })}>
                Tout effacer
              </button>
            </div>
          )}

          {data && data.total === 0 ? (
            <EmptyState
              icon={FileStack}
              title={hasActiveFilters(params) ? "Aucun résultat" : "Aucun document ici"}
              description={hasActiveFilters(params) ? "Essayez d'autres mots-clés ou retirez des filtres." : "Déposez des fichiers : ils seront analysés et indexés automatiquement."}
              action={!hasActiveFilters(params) && can("document:create") ? <Button onClick={() => setUploadOpen(true)}><Upload /> Déposer</Button> : undefined}
            />
          ) : (
            <>
              <DocumentTable
                items={data?.items}
                loading={isLoading}
                sort={filters.sort ?? "created_at"}
                order={filters.order ?? "desc"}
                onSort={(f) => setFilters({ sort: f, order: filters.sort === f && filters.order === "desc" ? "asc" : "desc" })}
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
              {data && (
                <Pagination page={page} pageSize={data.page_size} total={data.total}
                            onPage={(p) => { const n = new URLSearchParams(params); n.set("page", String(p)); setParams(n, { replace: true }); }} />
              )}
            </>
          )}
        </Card>
      </div>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} defaultFolder={filters.folder_id ?? null} />
      <AdvancedFilters open={advancedOpen} onOpenChange={setAdvancedOpen} value={filters} onApply={(f) => setFilters(f)} />
    </div>
  );
}
