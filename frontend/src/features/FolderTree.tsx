import { useMemo, useState } from "react";
import { ChevronRight, Folder as FolderIcon, FolderOpen, FolderPlus, Library, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useFolders, useInvalidateDocs } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { Folder } from "@/types/api";
import { cn } from "@/utils/format";
import { Button, Field, Input } from "@/components/ui/primitives";
import { ConfirmDialog, Dialog, DropdownContent, DropdownItem, DropdownMenu, DropdownTrigger } from "@/components/ui/overlay";

interface Props {
  selected: string | null;
  onSelect: (id: string | null) => void;
}

export function FolderTree({ selected, onSelect }: Props) {
  const { data: folders = [] } = useFolders();
  const can = useCan();
  const invalidate = useInvalidateDocs();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [editor, setEditor] = useState<{ mode: "create" | "rename"; parent?: string | null; folder?: Folder } | null>(null);
  const [toDelete, setToDelete] = useState<Folder | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const children = useMemo(() => {
    const map = new Map<string | null, Folder[]>();
    folders.forEach((f) => map.set(f.parent_id, [...(map.get(f.parent_id) ?? []), f]));
    return map;
  }, [folders]);

  const toggle = (id: string) =>
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const save = async () => {
    if (!editor || !name.trim()) return;
    setBusy(true);
    try {
      if (editor.mode === "create") {
        const f = await api<Folder>("/folders", { method: "POST", body: { name, parent_id: editor.parent ?? null } });
        if (editor.parent) setExpanded((s) => new Set(s).add(editor.parent!));
        onSelect(f.id);
      } else if (editor.folder) {
        await api(`/folders/${editor.folder.id}`, { method: "PATCH", body: { name } });
      }
      invalidate();
      setEditor(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!toDelete) return;
    setBusy(true);
    try {
      const r = await api<{ message: string }>(`/folders/${toDelete.id}`, { method: "DELETE" });
      toast.success(r.message);
      if (selected === toDelete.id) onSelect(null);
      invalidate();
      setToDelete(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const renderNode = (f: Folder, depth: number) => {
    const kids = children.get(f.id) ?? [];
    const open = expanded.has(f.id);
    const active = selected === f.id;
    return (
      <li key={f.id}>
        <div
          className={cn(
            "group flex items-center gap-1 rounded-md py-1 pr-1 text-sm",
            active ? "bg-accent text-accent-foreground" : "hover:bg-muted",
          )}
          style={{ paddingLeft: depth * 14 + 4 }}
        >
          <button
            className={cn("rounded p-0.5 text-muted-foreground", !kids.length && "invisible")}
            onClick={() => toggle(f.id)}
            aria-label={open ? "Replier" : "Déplier"}
          >
            <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          </button>
          <button className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => onSelect(f.id)}>
            {active ? <FolderOpen className="size-4 shrink-0 text-primary" /> : <FolderIcon className="size-4 shrink-0 text-muted-foreground" />}
            <span className="truncate">{f.name}</span>
            {f.document_count > 0 && <span className="ml-auto text-xs tabular text-muted-foreground">{f.document_count}</span>}
          </button>
          {(can("folder:create") || can("folder:update") || can("folder:delete")) && (
            <DropdownMenu>
              <DropdownTrigger asChild>
                <button className="rounded p-0.5 text-muted-foreground opacity-0 hover:bg-background group-hover:opacity-100 data-[state=open]:opacity-100" aria-label="Actions du dossier">
                  <MoreHorizontal className="size-4" />
                </button>
              </DropdownTrigger>
              <DropdownContent>
                {can("folder:create") && (
                  <DropdownItem onSelect={() => { setName(""); setEditor({ mode: "create", parent: f.id }); }}>
                    <FolderPlus /> Nouveau sous-dossier
                  </DropdownItem>
                )}
                {can("folder:update") && (
                  <DropdownItem onSelect={() => { setName(f.name); setEditor({ mode: "rename", folder: f }); }}>
                    <Pencil /> Renommer
                  </DropdownItem>
                )}
                {can("folder:delete") && can("document:delete") && (
                  <DropdownItem destructive onSelect={() => setToDelete(f)}>
                    <Trash2 /> Supprimer
                  </DropdownItem>
                )}
              </DropdownContent>
            </DropdownMenu>
          )}
        </div>
        {open && kids.length > 0 && <ul>{kids.map((k) => renderNode(k, depth + 1))}</ul>}
      </li>
    );
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-2 pb-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Dossiers</span>
        {can("folder:create") && (
          <Button variant="ghost" size="icon" className="size-7" aria-label="Nouveau dossier"
                  onClick={() => { setName(""); setEditor({ mode: "create", parent: null }); }}>
            <FolderPlus />
          </Button>
        )}
      </div>
      <button
        onClick={() => onSelect(null)}
        className={cn("mb-1 flex items-center gap-2 rounded-md px-2 py-1.5 text-sm", selected === null ? "bg-accent text-accent-foreground" : "hover:bg-muted")}
      >
        <Library className="size-4" /> Tous les documents
      </button>
      <ul className="scrollbar-thin flex-1 overflow-y-auto">{(children.get(null) ?? []).map((f) => renderNode(f, 0))}</ul>

      <Dialog
        open={!!editor}
        onOpenChange={(o) => !o && setEditor(null)}
        title={editor?.mode === "create" ? "Nouveau dossier" : "Renommer le dossier"}
        size="sm"
        footer={
          <>
            <Button variant="outline" onClick={() => setEditor(null)}>Annuler</Button>
            <Button onClick={save} loading={busy} disabled={!name.trim()}>Enregistrer</Button>
          </>
        }
      >
        <form onSubmit={(e) => { e.preventDefault(); save(); }}>
          <Field label="Nom" htmlFor="folder-name">
            <Input id="folder-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus maxLength={255} />
          </Field>
        </form>
      </Dialog>
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Supprimer le dossier ?"
        description={`« ${toDelete?.name} » et ses sous-dossiers seront supprimés. Les documents qu'ils contiennent seront placés dans la corbeille.`}
        confirmLabel="Supprimer"
        destructive
        loading={busy}
        onConfirm={remove}
      />
    </div>
  );
}
