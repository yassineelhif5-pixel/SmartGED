import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Bookmark, BookmarkPlus, Check, MoreHorizontal, Pencil, Save, Star, StarOff, Trash2, User, Users } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useViews } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { DocumentFilters, DocumentView } from "@/types/api";
import { cn } from "@/utils/format";
import { Badge, Button, Field, Input, Switch, Textarea } from "@/components/ui/primitives";
import { ConfirmDialog, Dialog, DropdownContent, DropdownItem, DropdownLabel, DropdownMenu, DropdownSeparator, DropdownTrigger } from "@/components/ui/overlay";
import { sameFilters } from "./filters";

interface Props {
  activeViewId: string | null;
  current: DocumentFilters;
  onApply: (view: DocumentView | null) => void;
}

type Editor = { id?: string; name: string; description: string; scope: "tenant" | "personal"; is_default: boolean; filters: DocumentFilters };

/** Saved views: shared views configured by tenant admins + the user's personal views. */
export function ViewsBar({ activeViewId, current, onApply }: Props) {
  const { data } = useViews();
  const can = useCan();
  const qc = useQueryClient();
  const canShare = can("document_view:administer");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [toDelete, setToDelete] = useState<DocumentView | null>(null);
  const [busy, setBusy] = useState(false);
  const views = data?.views ?? [];
  const shared = views.filter((v) => v.scope === "tenant");
  const personal = views.filter((v) => v.scope === "personal");
  const active = views.find((v) => v.id === activeViewId) ?? null;
  const dirty = !!active && !sameFilters(active.filters, current);
  const refresh = () => qc.invalidateQueries({ queryKey: ["document-views"] });

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
      refresh();
      return true;
    } catch (e) {
      toast.error((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!editor) return;
    const body = { name: editor.name, description: editor.description || null, scope: editor.scope, is_default: editor.is_default, filters: editor.filters };
    let saved: DocumentView | null = null;
    const ok = await run(async () => {
      saved = await api<DocumentView>(editor.id ? `/document-views/${editor.id}` : "/document-views", { method: editor.id ? "PUT" : "POST", body });
    }, editor.scope === "tenant" ? "Vue partagée avec l'organisation" : "Vue personnelle enregistrée");
    if (ok) {
      setEditor(null);
      if (saved) onApply(saved);
    }
  };

  const setMyDefault = (v: DocumentView | null) =>
    run(() => api("/document-views/me/default", { method: "PUT", body: { view_id: v?.id ?? null } }),
        v ? `« ${v.name} » s'ouvrira par défaut` : "Aucune vue par défaut");

  const chip = (v: DocumentView) => (
    <button
      key={v.id}
      onClick={() => onApply(activeViewId === v.id ? null : v)}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1 text-xs font-medium transition-colors",
        activeViewId === v.id ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-muted",
      )}
      title={v.description ?? undefined}
    >
      {v.scope === "tenant" ? <Users className="size-3" /> : <User className="size-3" />}
      {v.name}
      {data?.default_view_id === v.id && <Star className="size-3 fill-current" aria-label="Vue par défaut" />}
    </button>
  );

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <Bookmark className="size-4 text-muted-foreground" />
      <button
        onClick={() => onApply(null)}
        className={cn("rounded-full border px-3 py-1 text-xs font-medium", !activeViewId ? "border-primary bg-accent text-accent-foreground" : "bg-card hover:bg-muted")}
      >
        Tous
      </button>
      {shared.map(chip)}
      {personal.length > 0 && shared.length > 0 && <span className="mx-1 h-4 w-px bg-border" />}
      {personal.map(chip)}

      {active && dirty && active.can_edit && (
        <Button size="sm" variant="outline" className="h-7" loading={busy}
                onClick={() => run(() => api(`/document-views/${active.id}`, { method: "PUT", body: { ...active, filters: current } }), "Vue mise à jour")}>
          <Save /> Mettre à jour « {active.name} »
        </Button>
      )}
      <Button size="sm" variant="ghost" className="h-7"
              onClick={() => setEditor({ name: "", description: "", scope: "personal", is_default: false, filters: current })}>
        <BookmarkPlus /> Enregistrer la vue
      </Button>

      <DropdownMenu>
        <DropdownTrigger asChild>
          <Button size="icon" variant="ghost" className="size-7" aria-label="Gérer les vues"><MoreHorizontal /></Button>
        </DropdownTrigger>
        <DropdownContent>
          <DropdownLabel>Ma vue par défaut</DropdownLabel>
          {views.map((v) => (
            <DropdownItem key={v.id} onSelect={() => setMyDefault(v)}>
              {data?.default_view_id === v.id ? <Check /> : <span className="size-4" />} {v.name}
              {v.scope === "tenant" && v.is_default && <Badge tone="outline" className="ml-auto">organisation</Badge>}
            </DropdownItem>
          ))}
          <DropdownItem onSelect={() => setMyDefault(null)}><StarOff /> Aucune (tous les documents)</DropdownItem>
          {data?.default_source === "user" && (
            <DropdownItem onSelect={() => run(() => api("/document-views/me/default", { method: "DELETE" }), "Vue par défaut de l'organisation rétablie")}>
              <Users /> Revenir au défaut de l'organisation
            </DropdownItem>
          )}
          {active?.can_edit && (
            <>
              <DropdownSeparator />
              <DropdownLabel>Vue active</DropdownLabel>
              <DropdownItem onSelect={() => setEditor({ id: active.id, name: active.name, description: active.description ?? "", scope: active.scope, is_default: active.is_default, filters: current })}>
                <Pencil /> Modifier « {active.name} »
              </DropdownItem>
              <DropdownItem destructive onSelect={() => setToDelete(active)}><Trash2 /> Supprimer</DropdownItem>
            </>
          )}
        </DropdownContent>
      </DropdownMenu>

      <Dialog open={!!editor} onOpenChange={(o) => !o && setEditor(null)} title={editor?.id ? "Modifier la vue" : "Enregistrer la vue"}
              description="La vue mémorise la recherche, les filtres, le dossier et le tri actuellement affichés."
              footer={<><Button variant="outline" onClick={() => setEditor(null)}>Annuler</Button><Button loading={busy} disabled={!editor?.name.trim()} onClick={save}>Enregistrer</Button></>}>
        {editor && (
          <div className="space-y-4">
            <Field label="Nom"><Input autoFocus maxLength={120} value={editor.name} onChange={(e) => setEditor({ ...editor, name: e.target.value })} placeholder="Ex. Factures du trimestre" /></Field>
            <Field label="Description"><Textarea rows={2} maxLength={500} value={editor.description} onChange={(e) => setEditor({ ...editor, description: e.target.value })} /></Field>
            {canShare ? (
              <div className="space-y-3 rounded-md border p-3">
                <label className="flex items-center gap-3 text-sm">
                  <Switch checked={editor.scope === "tenant"} onChange={(v) => setEditor({ ...editor, scope: v ? "tenant" : "personal", is_default: v && editor.is_default })} />
                  <span><span className="font-medium">Partager avec toute l'organisation</span><span className="block text-xs text-muted-foreground">Visible par tous les membres, modifiable par les administrateurs uniquement.</span></span>
                </label>
                {editor.scope === "tenant" && (
                  <label className="flex items-center gap-3 text-sm">
                    <Switch checked={editor.is_default} onChange={(v) => setEditor({ ...editor, is_default: v })} />
                    <span><span className="font-medium">Vue par défaut de l'organisation</span><span className="block text-xs text-muted-foreground">Ouverte automatiquement, sauf pour les utilisateurs ayant choisi leur propre défaut.</span></span>
                  </label>
                )}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Cette vue sera personnelle : vous seul la verrez.</p>
            )}
          </div>
        )}
      </Dialog>
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} destructive loading={busy}
                     title="Supprimer la vue ?" confirmLabel="Supprimer"
                     description={toDelete?.scope === "tenant" ? "Cette vue partagée disparaîtra pour tous les membres." : "Cette vue personnelle sera supprimée."}
                     onConfirm={async () => { if (await run(() => api(`/document-views/${toDelete!.id}`, { method: "DELETE" }), "Vue supprimée")) { setToDelete(null); onApply(null); } }} />
    </div>
  );
}
