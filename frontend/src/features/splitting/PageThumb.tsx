import { useEffect, useRef, useState } from "react";
import { fetchBlob } from "@/api/client";
import { cn } from "@/utils/format";

/** Lazily rendered page thumbnail (fetched with the bearer token, shown from a blob URL). */
export function PageThumb({ docId, page, excerpt, dimmed }: { docId: string; page: number; excerpt: string; dimmed?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setVisible(true), { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchBlob(`/documents/${docId}/pages/${page}/thumbnail`, { width: 220 })
      .then((b) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(b);
        setUrl(objectUrl);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [visible, docId, page]);

  return (
    <div ref={ref} className={cn("relative aspect-[1/1.414] w-full overflow-hidden rounded-md border bg-white shadow-sm", dimmed && "opacity-40")}>
      {url ? (
        <img src={url} alt={`Page ${page}`} className="h-full w-full object-contain" draggable={false} />
      ) : (
        <div className="h-full overflow-hidden p-2 text-[9px] leading-snug text-muted-foreground">
          {failed ? excerpt || "Page vide" : <span className="block h-full animate-pulse rounded bg-muted" />}
        </div>
      )}
    </div>
  );
}
