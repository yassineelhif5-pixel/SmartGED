import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, CloudUpload, FileText, Loader2, X, XCircle } from "lucide-react";
import { api, ApiError } from "@/api/client";
import { useDocumentTypes, useFolders, useInvalidateDocs } from "@/hooks/queries";
import type { DocumentDetail } from "@/types/api";
import { cn, formatBytes } from "@/utils/format";
import { Button, Field, Input, Select } from "@/components/ui/primitives";
import { Dialog } from "@/components/ui/overlay";

type Item = { file: File; state: "queued" | "uploading" | "done" | "error"; message?: string; doc?: DocumentDetail };

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.txt,.csv,.md,.docx,.xlsx,.pptx,.eml";

export function UploadDialog({
  open,
  onOpenChange,
  defaultFolder,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  defaultFolder: string | null;
}) {
  const { data: folders = [] } = useFolders();
  const { data: types = [] } = useDocumentTypes();
  const invalidate = useInvalidateDocs();
  const [items, setItems] = useState<Item[]>([]);
  const [folder, setFolder] = useState<string>(defaultFolder ?? "");
  const [docType, setDocType] = useState("");
  const [tags, setTags] = useState("");
  const [dragging, setDragging] = useState(false);
  const [running, setRunning] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) setFolder(defaultFolder ?? "");
  }, [open, defaultFolder]);

  const add = useCallback((files: FileList | File[]) => {
    setItems((prev) => [...prev, ...Array.from(files).map((file) => ({ file, state: "queued" as const }))]);
  }, []);

  const start = async () => {
    setRunning(true);
    for (let i = 0; i < items.length; i++) {
      if (items[i].state === "done") continue;
      setItems((prev) => prev.map((it, j) => (j === i ? { ...it, state: "uploading" } : it)));
      const fd = new FormData();
      fd.append("file", items[i].file);
      if (folder) fd.append("folder_id", folder);
      if (docType) fd.append("document_type_id", docType);
      if (tags.trim()) fd.append("tags", tags);
      try {
        const doc = await api<DocumentDetail>("/documents", { method: "POST", body: fd });
        setItems((prev) =>
          prev.map((it, j) =>
            j === i
              ? { ...it, state: "done", doc, message: doc.duplicate_of_id ? "Doublon d'un document existant" : undefined }
              : it,
          ),
        );
      } catch (e) {
        setItems((prev) =>
          prev.map((it, j) => (j === i ? { ...it, state: "error", message: e instanceof ApiError ? e.message : "Erreur" } : it)),
        );
      }
    }
    setRunning(false);
    invalidate();
  };

  const close = (o: boolean) => {
    if (running) return;
    onOpenChange(o);
    if (!o) {
      setItems([]);
      setDocType("");
      setTags("");
      setFolder(defaultFolder ?? "");
    }
  };

  const done = items.length > 0 && items.every((i) => i.state === "done" || i.state === "error");

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title="Déposer des documents"
      description="Chaque fichier est contrôlé, haché (SHA-256), stocké puis envoyé au pipeline OCR."
      size="lg"
      footer={
        done ? (
          <Button onClick={() => close(false)}>Terminer</Button>
        ) : (
          <>
            <Button variant="outline" onClick={() => close(false)} disabled={running}>Annuler</Button>
            <Button onClick={start} loading={running} disabled={!items.length}>
              Déposer {items.length > 0 && `(${items.length})`}
            </Button>
          </>
        )
      }
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Dossier">
          <Select value={folder} onChange={(e) => setFolder(e.target.value)} disabled={running}>
            <option value="">Racine</option>
            {folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </Select>
        </Field>
        <Field label="Type documentaire" hint="Sinon : classification IA (phase 3)">
          <Select value={docType} onChange={(e) => setDocType(e.target.value)} disabled={running}>
            <option value="">À déterminer</option>
            {types.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </Field>
        <Field label="Tags" hint="Séparés par des virgules">
          <Input value={tags} onChange={(e) => setTags(e.target.value)} disabled={running} placeholder="finance, 2026" />
        </Field>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); add(e.dataTransfer.files); }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        className={cn(
          "mt-5 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
          dragging ? "border-primary bg-accent" : "border-border hover:border-primary/50 hover:bg-muted/50",
        )}
      >
        <CloudUpload className="size-8 text-primary" />
        <p className="mt-3 text-sm font-medium">Glissez-déposez vos fichiers ici</p>
        <p className="mt-1 text-xs text-muted-foreground">PDF, images (OCR), Office, texte — 100 Mo max par fichier</p>
        <input ref={inputRef} type="file" multiple accept={ACCEPT} className="hidden"
               onChange={(e) => e.target.files && add(e.target.files)} />
      </div>

      {items.length > 0 && (
        <ul className="mt-4 divide-y rounded-lg border">
          {items.map((it, i) => (
            <li key={i} className="flex items-center gap-3 px-3 py-2.5 text-sm">
              <FileText className="size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{it.file.name}</div>
                <div className={cn("text-xs", it.state === "error" ? "text-destructive" : "text-muted-foreground")}>
                  {it.message ?? formatBytes(it.file.size)}
                </div>
              </div>
              {it.state === "uploading" && <Loader2 className="size-4 animate-spin text-primary" />}
              {it.state === "done" && <CheckCircle2 className="size-4 text-success" />}
              {it.state === "error" && <XCircle className="size-4 text-destructive" />}
              {it.state === "queued" && !running && (
                <button aria-label="Retirer" onClick={() => setItems((p) => p.filter((_, j) => j !== i))}>
                  <X className="size-4 text-muted-foreground" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}
