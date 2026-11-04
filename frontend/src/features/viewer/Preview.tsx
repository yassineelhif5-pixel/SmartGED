import { useEffect, useState } from "react";
import { FileWarning, RotateCw, ZoomIn, ZoomOut } from "lucide-react";
import { fetchBlob } from "@/api/client";
import type { DocumentDetail } from "@/types/api";
import { Button, Spinner } from "@/components/ui/primitives";

/** Secure preview: the file is fetched with the bearer token and rendered from a blob URL. */
export function Preview({ doc, version }: { doc: DocumentDetail; version: number }) {
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const isPdf = doc.mime_type === "application/pdf";
  const isImage = doc.mime_type.startsWith("image/") && doc.mime_type !== "image/tiff";
  const isText = doc.mime_type.startsWith("text/");
  const previewable = isPdf || isImage || isText;

  useEffect(() => {
    if (!previewable) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    setError(null);
    fetchBlob(`/documents/${doc.id}/download`, { inline: true, version })
      .then(async (blob) => {
        if (cancelled) return;
        if (isText) setText(await blob.text());
        else {
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        }
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [doc.id, version, previewable, isText]);

  if (!previewable)
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-sm text-muted-foreground">
        <FileWarning className="size-8" />
        Aperçu non disponible pour ce format ({doc.extension.toUpperCase()}). Le texte extrait est consultable dans l'onglet « Texte ».
      </div>
    );
  if (error) return <div className="p-8 text-center text-sm text-destructive">{error}</div>;
  if (!url && text === null)
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="size-6" />
      </div>
    );

  if (isPdf) return <iframe title="Aperçu PDF" src={`${url}#toolbar=1&view=FitH`} className="h-full w-full border-0" />;
  if (isText)
    return <pre className="h-full overflow-auto whitespace-pre-wrap p-6 font-mono text-xs leading-relaxed">{text}</pre>;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b bg-card px-3 py-1.5">
        <Button variant="ghost" size="icon" aria-label="Zoom arrière" onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}><ZoomOut /></Button>
        <span className="tabular w-12 text-center text-xs">{Math.round(zoom * 100)} %</span>
        <Button variant="ghost" size="icon" aria-label="Zoom avant" onClick={() => setZoom((z) => Math.min(4, z + 0.25))}><ZoomIn /></Button>
        <Button variant="ghost" size="icon" aria-label="Pivoter" onClick={() => setRotation((r) => (r + 90) % 360)}><RotateCw /></Button>
      </div>
      <div className="flex flex-1 items-start justify-center overflow-auto bg-muted/40 p-6">
        <img
          src={url!}
          alt={doc.title}
          style={{ transform: `scale(${zoom}) rotate(${rotation}deg)`, transformOrigin: "top center" }}
          className="max-w-full shadow-lg transition-transform"
        />
      </div>
    </div>
  );
}
